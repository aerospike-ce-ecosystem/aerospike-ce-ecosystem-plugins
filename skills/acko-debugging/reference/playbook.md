# Debugging playbook — full command detail

Command blocks for each step of the 6-step procedure in `../SKILL.md`. `{ctx}` = resolved ackoctl context (omit `--context` for current-context).

## Step 1 — Gather cluster overview

**Data-plane discovery via ackoctl.** The user must have a connection profile registered with cluster-manager (created via the UI or `ackoctl connection create`).

If the user has not specified a `CONN_ID`, list available profiles first:

```bash
# 1. Find an existing connection profile to drive the diagnosis
ackoctl --context={ctx} connection list
# 2. If the list is empty, create one (mutation — confirm first):
#    ackoctl connection create --name <name> --host <host> --port 3000
```

Then run discovery against the selected `CONN_ID`:

```bash
ackoctl --context={ctx} cluster info <CONN_ID> -o yaml
ackoctl --context={ctx} info <CONN_ID> --command='statistics'
ackoctl --context={ctx} info <CONN_ID> --command='status'
```

Use `statistics` output to see `cluster_size`, `migration_status`, `stop_writes`, etc. across all nodes. `cluster info` already aggregates nodes, namespaces, sets and sindex counts.

**K8s-plane status — prefer ackoctl** (cluster-manager started with `K8S_MANAGEMENT_ENABLED=true`):

```bash
ackoctl --context={ctx} k8s cluster list                                            # all CRs in the workspace
ackoctl --context={ctx} k8s cluster list --workspace=<ws>                           # explicit workspace filter
ackoctl --context={ctx} k8s cluster get <ns>/<name> -o yaml                         # phase, size, conditions, dynamicConfigStatus
ackoctl --context={ctx} k8s cluster events <ns>/<name> --since=30m                  # classified events
ackoctl --context={ctx} k8s cluster logs <ns>/<name> --pod=<pod> --container=aerospike-server --since=5m --tail=200
```

The CR phase, size, conditions, and migration status are all in the `k8s cluster get` payload — no need to shell out for every field.

**`kubectl` fallback** (when K8s tools aren't exposed): `kubectl get asc <name> -n <ns> -o jsonpath='{.status.phase}'` (or `.phaseReason` / `.conditions` / `.size` / `.migrationStatus` / `.aerospikeClusterSize`).

## Step 2 — Phase branches

### Phase = `Error`

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.lastReconcileError}'
kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp' | tail -20
```

Check for invalid `aerospikeConfig` (parse errors), image pull failures, resource quota, webhook failures. The reconcile circuit breaker surfaces as `phase=BackoffActive`, not `Error`.

### Phase = `BackoffActive` (circuit breaker)

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions[?(@.type=="ReconcileHealthy")]}' | jq
```

- `ReconcileHealthy=True` → transient (pod not ready, image pull, capacity); auto-retries with backoff (capped at 5 min).
- `ReconcileHealthy=False, reason=PermanentError` → validation/configgen/Secret error; no retry. Fix the root cause, then toggle `spec.paused: true → null` (clears stale `failedReconcileCount`/`lastReconcileError`) or edit the spec.

### Phase = `ACLSync` (stuck)

ACL sync is failing — the cluster does **not** reach `Completed` while ACL is unsynced; it requeues ~30s. Check the `ACLSynced` condition, `ACLSyncError` event, and that the password Secret exists with the right key.

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions[?(@.type=="ACLSynced")]}' | jq
```

### Phase = `WaitingForMigration`

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.migrationStatus}' | jq .
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq 'to_entries[] | {pod: .key, migrating: .value.migratingPartitions}'
ackoctl --context={ctx} info <CONN_ID> --command='statistics' | tr ';' '\n' | grep migrate
```

Usually normal during scale-down. Report `migrationStatus.remainingPartitions` progress and advise waiting. Unparseable migrate stats are treated conservatively as "still migrating".

### Phase = `InProgress` (stuck > 5 minutes)

```bash
kubectl get pods -n <ns> -l aerospike.io/cr-name=<name> -o wide
kubectl get pvc -n <ns> -l aerospike.io/cr-name=<name>
kubectl describe pod <pending-or-failing-pod> -n <ns> | tail -30
kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=100
```

Check for: Pending PVCs (StorageClass not found or no capacity), ImagePullBackOff (wrong image name or no pull secret), scheduling failures (insufficient CPU/memory, node affinity mismatch).

### Phase = `Completed` but user reports issues

**Prefer ackoctl** for data-plane probes:

```bash
ackoctl --context={ctx} info <CONN_ID> --command='status'
ackoctl --context={ctx} info <CONN_ID> --command='statistics'
ackoctl --context={ctx} info <CONN_ID> --command='namespace/<ns-name>'
# Sample-record sanity check
ackoctl --context={ctx} query exec <CONN_ID> --namespace=<ns-name> --set=<set> --max-records=5
# Filtered probe — narrow in on records matching a suspected fault signal
ackoctl --context={ctx} query exec <CONN_ID> \
  --namespace=<ns-name> --set=<set> \
  --bin=age --op=between --value=18 --value2=99 \
  --select=name,age --max-records=20
```

When `query exec` returns a truncation marker, the result set was capped by `--max-records` (or the server-side ceiling) — there are more matching records than you asked to see. Tighten the predicate or raise `--max-records`; don't report the partial set as the whole picture.

`kubectl exec` fallback (only if `ackoctl` is unavailable):

```bash
kubectl get pods -n <ns> -l aerospike.io/cr-name=<name>
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v status
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep cluster_size
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'namespace/<ns-name>'
```

Check for: split cluster (`cluster_size` mismatch across pods), namespace stop-writes (near capacity), connection issues (`proto-fd-max` reached).

### Phase = `ConfigDegraded`

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions[?(@.type=="DynamicConfigDegraded")]}' | jq
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' | jq
```

See the ConfigDegraded branch in `../SKILL.md` for meaning and recovery (reconcile is halted until manual intervention).

## Step 3 — Pod-level issues

For any pods not in `Running` state — prefer ackoctl, fall back to kubectl:

```bash
# ackoctl path
ackoctl --context={ctx} k8s cluster logs <ns>/<name> --pod=<pod> --container=aerospike-server --since=10m --tail=200
ackoctl --context={ctx} k8s cluster logs <ns>/<name> --pod=<pod> --container=aerospike-server --previous   # if CrashLoopBackOff

# kubectl fallback
kubectl describe pod <pod> -n <ns>
kubectl logs -n <ns> <pod> -c aerospike-server
kubectl logs -n <ns> <pod> -c aerospike-server --previous
```

Common: **CrashLoopBackOff** (config parse error — check removed 7.x parameters in CE 8.1 — OOM, or `data-size` below 512 MiB minimum), **ImagePullBackOff** (wrong image / missing imagePullSecret), **Pending** (insufficient resources or PVC not bound).

## Step 4 — Operator logs

```bash
kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=200
```

Look for reconciliation errors, webhook rejection messages, resource creation failures.

## Step 5 — Events timeline

**Prefer ackoctl** (classifies each event into `Rolling Restart`, `Configuration`, `Scaling`, `Network`, `Rack Management`, …):

```bash
ackoctl --context={ctx} k8s cluster events <ns>/<name> --since=60m
```

`kubectl` fallback (raw, unclassified):

```bash
kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp'
```

## Step 6 — Dynamic config status

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq '.[].dynamicConfigStatus'
```

If `Failed`, the changed parameter is not dynamically changeable. Advise `enableDynamicConfigUpdate: false` to force a rolling restart.
