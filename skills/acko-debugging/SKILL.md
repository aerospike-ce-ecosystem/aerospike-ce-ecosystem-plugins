---
name: acko-debugging
description: "Systematic 6-step diagnosis procedure for ACKO-managed Aerospike CE clusters, with CE 8.1-specific pitfalls and a remediation matrix. Routes data-plane and K8s-plane probes through ACM MCP tools when registered, and falls back to kubectl/asinfo otherwise. MUST USE when the user reports CrashLoopBackOff, AerospikeCluster CRD phase=Error / WaitingForMigration / InProgress stuck, dynamic config rollback failed, ConfigDegraded, circuit breaker active, namespace stop-writes, split cluster, ACLSyncError, RestartFailed, ReadinessGateBlocking, ScaleDownDeferred, operator log errors, webhook rejection, or any troubleshooting flow that resolves to running diagnostic commands or queries against an ACKO Aerospike cluster. Triggers on: 'CrashLoopBackOff', 'phase=Error', 'reconcile failure', 'cluster won''t start', 'pods stuck', 'migration stuck', 'dynamic config failed', 'CE 8.1 config error', 'AerospikeCluster reconcile', 'debug aerospike cluster', 'troubleshoot ACKO'."
---

# ACKO Cluster Debugging Procedure

This skill provides the systematic procedure to follow when an ACKO-managed Aerospike CE cluster reports a problem. It encodes:

1. The 6-step ordering Aerospike SREs use during real outages,
2. The CE 8.1-specific config pitfalls that surface as cryptic boot failures,
3. A remediation matrix mapping observed symptoms to concrete fixes.

For routine reads (`list_k8s_clusters`, `get_k8s_pods` etc.) the MCP tools are self-describing and you do **not** need this skill — call them directly. Load this skill when something is actually broken.

## Tool routing — MCP first, kubectl fallback

When ACM MCP is registered (`mcp__aerospike-*` tools available in the session) prefer it for *both* planes:

* **Data plane** — `list_namespaces`, `get_nodes`, `execute_info`, `query`, `get_record`, `record_exists`, `list_sets`.
* **K8s plane** — `list_k8s_clusters`, `get_k8s_pods`, `get_k8s_events`, `get_k8s_logs`, `scale_k8s_cluster`. These five are exposed only when the ACM deployment runs with `K8S_MANAGEMENT_ENABLED=true`. If `tools/list` for the chosen prefix does not include them, fall back to `kubectl` for the K8s plane.

If **no `mcp__aerospike-*` tools are available** in this session, tell the user:

> ACM MCP is not registered in this session. Run `/acm-mcp-init` (or invoke the `acm-mcp-init` skill) to register one or more cluster-manager endpoints, then retry. You may still proceed with `kubectl`-only diagnosis, but data-plane probes (`asinfo`, record sampling, query) will be limited to `kubectl exec` rather than the typed MCP layer.

## Cluster selection

Many users run multi-cluster ACKO. The user's wording usually indicates which cluster — phrases like "in dev", "production EU", "the prod-us cluster". Map the named cluster to the registered MCP prefix:

| User says | MCP prefix used |
|-----------|-----------------|
| "in dev" / "local" / "my workstation" | `mcp__aerospike-dev__*` |
| "in staging" | `mcp__aerospike-staging__*` |
| "in prod-us" / "production US" | `mcp__aerospike-prod-us__*` |

When multiple ACM endpoints could match or none is named, list registered endpoints (`claude mcp list`) and ask the user to disambiguate. Replace `{prefix}` below with the resolved prefix.

## Mutation tools — confirm before invoking

The MCP server enforces a **call-time** read/write gate. Under the default `READ_ONLY` profile the eleven mutation tools below return `MCPToolError(code="access_denied")` before the body runs — this is the safety net.

If the deployment is configured with `ACM_MCP_ACCESS_PROFILE=full` the server-side gate is *off* and only this skill's confirmation rule remains. **Always confirm with the user before invoking any of the eleven mutation tools**:

`create_connection`, `update_connection`, `delete_connection`, `create_record`, `update_record`, `delete_record`, `delete_bin`, `truncate_set`, `execute_info`, `execute_info_on_node`, `scale_k8s_cluster`.

`execute_info` is in the mutation list because asinfo can change cluster config (`set-config:`, `recluster:`, etc.); `scale_k8s_cluster` patches the AerospikeCluster CR's `spec.size` so it carries the same blast radius as a direct `kubectl patch`. For diagnostic asinfo reads under `READ_ONLY`, prefer `execute_info_read_only` (whitelisted verbs only) which is **not** in the mutation list.

## Debugging procedure

Execute these steps in order. Stop and report findings as soon as you identify the root cause.

### Step 1 — Gather cluster overview

**Data-plane discovery via MCP.** The user must have an active connection profile registered with ACM (created via the cluster-manager UI or the `create_connection` MCP tool).

If the user has not specified a `conn_id`, list available profiles first:

```
# 1. Find an existing connection profile to drive the diagnosis
mcp__aerospike-{prefix}__list_connections()
# 2. If the list is empty, ask the user to create one before continuing,
#    or create one inline with their input (mutation — confirm first):
#    mcp__aerospike-{prefix}__create_connection(name="<...>", hosts=["<...>"], port=3000)
```

Then run discovery against the selected `conn_id`:

```
mcp__aerospike-{prefix}__list_namespaces(conn_id="<conn>")
mcp__aerospike-{prefix}__get_nodes(conn_id="<conn>")
mcp__aerospike-{prefix}__execute_info(conn_id="<conn>", command="statistics")
```

Use `execute_info` results to see `cluster_size`, `migration_status`, `stop_writes`, etc. across all nodes.

**K8s-plane status — prefer MCP** (`K8S_MANAGEMENT_ENABLED=true` deployments only):

```
mcp__aerospike-{prefix}__list_k8s_clusters()
mcp__aerospike-{prefix}__list_k8s_clusters(workspace_id="<ws>")        # filter by workspace label
mcp__aerospike-{prefix}__get_k8s_pods(cluster_id="<ns>/<name>")        # phase/podIP/dynamicConfigStatus per pod
mcp__aerospike-{prefix}__get_k8s_events(cluster_id="<ns>/<name>", since_minutes=30)
mcp__aerospike-{prefix}__get_k8s_logs(cluster_id="<ns>/<name>", pod_name="<pod>", since_seconds=300, tail_lines=200)
```

`cluster_id` is `"<namespace>/<name>"`. The CR phase, size, conditions, and migration status are all in the `list_k8s_clusters` summary entry — there is no need to shell out for every field.

**`kubectl` fallback** (when MCP K8s tools are not exposed by the ACM deployment, or when fields the MCP summary doesn't surface yet are needed):

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
# Direct asinfo check
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep migrate
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

**Prefer MCP** for data-plane probes:

```
# Status, statistics, namespace details — per-node where useful.
mcp__aerospike-{prefix}__execute_info(conn_id="<conn>", command="status")
mcp__aerospike-{prefix}__execute_info(conn_id="<conn>", command="statistics")
mcp__aerospike-{prefix}__execute_info(conn_id="<conn>", command="namespace/<ns-name>")
# Sample-record sanity check
mcp__aerospike-{prefix}__query(conn_id="<conn>", namespace="<ns-name>", set_name="<set>", max_records=5)
# Filtered probe — predicate uses flat fields (predicate_bin / predicate_operator
# / predicate_value / predicate_value2). Useful for narrowing in on records that
# match a suspected fault signal, e.g. records past a TTL boundary.
mcp__aerospike-{prefix}__query(
    conn_id="<conn>",
    namespace="<ns-name>",
    set_name="<set>",
    predicate_bin="age", predicate_operator="between",
    predicate_value=18, predicate_value2=99,
    max_records=20,
)
```

When `query` returns `truncated: true`, the result set was capped by `max_records` (or the server-side ceiling). For diagnosis this usually means "there are more matching records than you asked to see"; either tighten the predicate or raise `max_records` for the next call. Don't silently report the partial set as the whole picture.

`kubectl exec` fallback (only if MCP path is unavailable):

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

For any pods not in `Running` state:

```bash
kubectl describe pod <pod> -n <ns>
kubectl logs -n <ns> <pod> -c aerospike-server
kubectl logs -n <ns> <pod> -c aerospike-server --previous   # if CrashLoopBackOff
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

**Prefer MCP** (already classifies each event into `Rolling Restart`, `Configuration`, `Scaling`, `Network`, `Rack Management`, …):

```
mcp__aerospike-{prefix}__get_k8s_events(cluster_id="<ns>/<name>", since_minutes=60)
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

## Output format

After completing the investigation, provide:

1. **Root cause** — clear description of what is wrong.
2. **Evidence** — the specific command output that shows the problem.
3. **Fix** — step-by-step remediation commands the user can run.
4. **Prevention** — how to avoid this issue in the future.
