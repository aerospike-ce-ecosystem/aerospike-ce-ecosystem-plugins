---
name: acko-debugging
description: "Systematic 6-step diagnosis procedure for ACKO-managed Aerospike CE clusters, with CE 8.1-specific pitfalls and a remediation matrix. Routes data-plane and K8s-plane probes through ackoctl (which calls cluster-manager — the authoritative source for AerospikeCluster state) and falls back to kubectl/asinfo when ackoctl is unavailable. MUST USE when the user reports CrashLoopBackOff, AerospikeCluster CRD phase=Error / WaitingForMigration / InProgress stuck, dynamic config rollback failed, ConfigDegraded, circuit breaker active, namespace stop-writes, split cluster, ACLSyncError, RestartFailed, ReadinessGateBlocking, ScaleDownDeferred, operator log errors, webhook rejection, or any troubleshooting flow that resolves to running diagnostic commands or queries against an ACKO Aerospike cluster. Triggers on: 'CrashLoopBackOff', 'phase=Error', 'reconcile failure', 'cluster won''t start', 'pods stuck', 'migration stuck', 'dynamic config failed', 'CE 8.1 config error', 'AerospikeCluster reconcile', 'debug aerospike cluster', 'troubleshoot ACKO'."
---

# ACKO Cluster Debugging Procedure

This skill provides the systematic procedure to follow when an ACKO-managed Aerospike CE cluster reports a problem. It encodes:

1. The 6-step ordering Aerospike SREs use during real outages,
2. The CE 8.1-specific config pitfalls that surface as cryptic boot failures,
3. A remediation matrix mapping observed symptoms to concrete fixes.

For routine reads (`ackoctl k8s cluster list`, `ackoctl record get`, …) the CLI is self-describing — use `ackoctl <noun> --help` for shape. Load this skill when something is actually broken.

## Tool routing — ackoctl first, kubectl fallback

Prefer `ackoctl` for **both** planes. It goes through cluster-manager, which is the authoritative source for AerospikeCluster state (it normalises CR status fields, classifies K8s events, and enforces workspace ACL). Fall back to `kubectl` / direct `asinfo` only when `ackoctl` is unavailable, or when a field the cluster-manager summary does not surface yet is needed.

- **Data plane** — `ackoctl cluster info`, `ackoctl info --command=...`, `ackoctl query exec`, `ackoctl record get`, `ackoctl set list`.
- **K8s plane** — `ackoctl k8s cluster list / get / reconcile / scale`, `ackoctl k8s cluster logs`, `ackoctl k8s events list`. Requires cluster-manager started with `K8S_MANAGEMENT_ENABLED=true`; if `ackoctl k8s cluster list` returns a 404, fall back to `kubectl` for the K8s plane.

If `ackoctl` is not installed or no context is configured, tell the user:

> ackoctl is not configured in this session. Install via `curl -fsSL https://raw.githubusercontent.com/aerospike-ce-ecosystem/ackoctl/main/install.sh | sh` and run `ackoctl config set-context <name> --server=<url> --token=<jwt> --workspace-id=<ws>` to point at a cluster-manager. You may proceed with `kubectl`-only diagnosis in the meantime, but data-plane probes (`asinfo`, record sampling, query) will go through `kubectl exec` rather than the typed cluster-manager surface.

The `ackoctl` skill covers install and configuration in full.

## Cluster selection

Many users run multi-cluster ACKO. The user's wording usually indicates which cluster — phrases like "in dev", "production EU", "the prod-us cluster". Map the named cluster to the configured ackoctl context:

| User says | ackoctl context used |
|-----------|----------------------|
| "in dev" / "local" / "my workstation" | `--context=kind-local` (or whatever is the current-context) |
| "in staging" | `--context=staging` |
| "in prod-us" / "production US" | `--context=prod-us` |

When multiple contexts could match or none is named, list configured contexts (`ackoctl config view -o yaml`) and ask the user to disambiguate. Below, replace `{ctx}` with the resolved context name — or omit `--context` to use the current-context.

## Mutation commands — confirm before invoking

These ackoctl invocations mutate cluster state. Always confirm with the user before running them — the workspace ACL on the server is the safety net, but blast radius is the user's call:

| Command | Blast radius |
|---------|--------------|
| `ackoctl record put` / `record delete` | Single-record write/delete |
| `ackoctl cluster configure-namespace` | Runtime config change on the live cluster (`asinfo set-config`) |
| `ackoctl info --allow-write` | Raw asinfo with mutation verbs (`set-config:`, `recluster:`) |
| `ackoctl index create` / `index delete` | Server-side index DDL |
| `ackoctl k8s cluster scale` | Patches `spec.size` on the AerospikeCluster CR — same blast radius as `kubectl patch` |
| `ackoctl k8s cluster reconcile` | Stamps `acko.io/force-reconcile`; triggers operator reconciliation |
| `ackoctl udf upload` / `udf remove` | Cluster-wide UDF module change |
| `ackoctl admin user/role *` | Identity changes (security-enabled clusters only) |
| `ackoctl connection delete` | Removes the profile **and** cascades all attached notes |

For diagnostic reads, prefer the no-side-effect verbs: `ackoctl k8s cluster get`, `ackoctl info` without `--allow-write` (whitelisted read verbs only), `ackoctl query exec`, `ackoctl record get`.

## Debugging procedure

Execute these steps in order. Stop and report findings as soon as you identify the root cause.

### Step 1 — Gather cluster overview

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
ackoctl --context={ctx} k8s events list <ns>/<name> --since=30m                     # classified events
ackoctl --context={ctx} k8s cluster logs <ns>/<name> --pod=<pod> --container=aerospike-server --since=5m --tail=200
```

The CR phase, size, conditions, and migration status are all in the `k8s cluster get` payload — no need to shell out for every field.

**`kubectl` fallback** (when cluster-manager's K8s tools are not exposed, or when fields the summary does not surface yet are needed):

```bash
kubectl get asc -n <ns>
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phase}'
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phaseReason}'
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions}' | jq .
kubectl get asc <name> -n <ns> -o jsonpath='{.status.size}'
kubectl get asc <name> -n <ns> -o jsonpath='{.status.migrationStatus}' | jq .
kubectl get asc <name> -n <ns> -o jsonpath='{.status.aerospikeClusterSize}'
```

### Step 2 — Branch based on phase

#### If Phase = `Error`

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.lastReconcileError}'
kubectl get asc <name> -n <ns> -o jsonpath='{.status.failedReconcileCount}'
kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp' | tail -20
```

Check for:
- Invalid `aerospikeConfig` (config parse errors)
- Image pull failures (wrong image name or registry access)
- Resource quota exceeded
- Webhook validation failures
- Circuit breaker activation (`failedReconcileCount >= 10`)

#### If Phase = `WaitingForMigration`

```bash
# Check cluster-level migration status
kubectl get asc <name> -n <ns> -o jsonpath='{.status.migrationStatus}' | jq .
# Per-pod migration partitions
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq 'to_entries[] | {pod: .key, migrating: .value.migratingPartitions}'
# Direct asinfo check via ackoctl
ackoctl --context={ctx} info <CONN_ID> --command='statistics' | tr ';' '\n' | grep migrate
```

This is usually normal during scale-down. Report `migrationStatus.remainingPartitions` progress and advise waiting.

#### If Phase = `InProgress` (stuck > 5 minutes)

```bash
kubectl get pods -n <ns> -l aerospike.io/cr-name=<name> -o wide
kubectl get pvc -n <ns> -l aerospike.io/cr-name=<name>
kubectl describe pod <pending-or-failing-pod> -n <ns> | tail -30
kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=100
```

Check for:
- Pending PVCs (StorageClass not found or no capacity)
- ImagePullBackOff (wrong image name or no pull secret)
- Scheduling failures (insufficient CPU/memory, node affinity mismatch)

#### If Phase = `Completed` but user reports issues

**Prefer ackoctl** for data-plane probes:

```bash
# Status, statistics, namespace details — per-node where useful.
ackoctl --context={ctx} info <CONN_ID> --command='status'
ackoctl --context={ctx} info <CONN_ID> --command='statistics'
ackoctl --context={ctx} info <CONN_ID> --command='namespace/<ns-name>'
# Sample-record sanity check
ackoctl --context={ctx} query exec <CONN_ID> --namespace=<ns-name> --set=<set> --max-records=5
# Filtered probe — useful for narrowing in on records that match a suspected
# fault signal, e.g. records past a TTL boundary.
ackoctl --context={ctx} query exec <CONN_ID> \
  --namespace=<ns-name> --set=<set> \
  --bin=age --op=between --value=18 --value2=99 \
  --select=name,age --max-records=20
```

When `query exec` returns a truncation marker, the result set was capped by `--max-records` (or the server-side ceiling). For diagnosis this usually means "there are more matching records than you asked to see"; either tighten the predicate or raise `--max-records` for the next call. Don't silently report the partial set as the whole picture.

`kubectl exec` fallback (only if `ackoctl` is unavailable):

```bash
kubectl get pods -n <ns> -l aerospike.io/cr-name=<name>
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v status
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep cluster_size
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'namespace/<ns-name>'
```

Check for:
- Split cluster (`cluster_size` mismatch across pods)
- Namespace stop-writes (near capacity)
- Connection issues (`proto-fd-max` reached)

#### If Phase = `ConfigDegraded`

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions[?(@.type=="DynamicConfigDegraded")]}' | jq
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' | jq
```

Meaning: a 2PC dynamic config update failed AND the LIFO rollback also failed. Different pods now hold different runtime configs. The operator will attempt a cold restart on the next reconcile to converge to spec. **Do not** manually flip `enableDynamicConfigUpdate` or re-apply the change — let the cold restart run. If the cold-restart loop continues, the underlying value is invalid for the deployed hardware shape — revert spec to the last known-good value and re-apply. Recovery is complete when `phase=Completed` and the `DynamicConfigDegraded` condition clears.

### Step 3 — Check pod-level issues

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

Common pod-level issues:
- **CrashLoopBackOff**: config parse error (check for removed 7.x parameters in CE 8.1), OOM, or `data-size` below 512 MiB minimum
- **ImagePullBackOff**: wrong image name or missing imagePullSecret
- **Pending**: insufficient resources or PVC not bound

### Step 4 — Check operator logs

```bash
kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=200
```

Look for:
- Reconciliation errors
- Webhook rejection messages
- Resource creation failures

### Step 5 — Check events timeline

**Prefer ackoctl** (already classifies each event into `Rolling Restart`, `Configuration`, `Scaling`, `Network`, `Rack Management`, …):

```bash
ackoctl --context={ctx} k8s events list <ns>/<name> --since=60m
```

`kubectl` fallback (raw, unclassified):

```bash
kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp'
```

Key events to look for:
- `CircuitBreakerActive`: 10+ consecutive failures, operator in backoff
- `RestartFailed`: pod restart failed during rolling update
- `ScaleDownDeferred`: migration blocking scale-down
- `DynamicConfigStatusFailed`: dynamic config change failed
- `ACLSyncError`: ACL synchronization failed
- `TemplateResolutionError`: template parsing failed
- `ReadinessGateBlocking`: readiness gate not satisfied

### Step 6 — Check dynamic config status (if applicable)

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq '.[].dynamicConfigStatus'
```

If status is `Failed`, the changed parameter is not dynamically changeable. Advise setting `enableDynamicConfigUpdate: false` to force a rolling restart.

## Remediation actions

After identifying the root cause, suggest the specific fix:

| Issue | Remediation |
|-------|-------------|
| Config parse error | Fix `aerospikeConfig` in CR and re-apply |
| Image pull failure | Fix image name or add imagePullSecret |
| PVC Pending | Check StorageClass exists and has capacity |
| Resource insufficient | Reduce resource requests or add nodes to K8s cluster |
| CE constraint violation | Fix CR to comply (size ≤ 8, namespaces ≤ 2, no xdr/tls, CE image) |
| Circuit breaker active | Fix root cause; operator auto-retries with backoff |
| Dynamic config failed | Set `enableDynamicConfigUpdate: false` for rolling restart |
| Split cluster | Verify network connectivity, check `cluster-name` consistency. Compare `status.aerospikeClusterSize` with `status.size` |
| Stop writes | Increase storage capacity or reduce data volume |
| ACL sync error | Verify Secret exists with correct password key |
| Operations stuck | Clear operations: `kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"operations":null}}'` |

## CE 8.1 common pitfalls

Always check for these CE 8.1-specific issues:

1. **`info` port block in config** — removed in 8.1. Causes parse error. Use `admin { port 3008 }` instead.
2. **`memory-size` used** — removed. Use `storage-engine memory { data-size N }` with integer bytes.
3. **`write-block-size` used** — replaced by `flush-size` in 7.1+.
4. **`data-size` below 512 MiB** — minimum is 536870912 bytes.
5. **`nsup-period=0` with `default-ttl!=0`** — server fails to start.
6. **Byte values as strings** — all sizes in `aerospikeConfig` must be integer bytes, not `"4G"` or `"1M"`.

Report the root cause with the command output that proves it, then the remediation commands.
