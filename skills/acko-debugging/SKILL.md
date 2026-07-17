---
name: acko-debugging
description: "Systematic 6-step diagnosis procedure for ACKO-managed Aerospike CE clusters, with CE 8.1-specific pitfalls and a remediation matrix. Routes data-plane and K8s-plane probes through ackoctl (which calls cluster-manager — the authoritative source for AerospikeCluster state) and falls back to kubectl/asinfo when ackoctl is unavailable. MUST USE when the user reports a broken ACKO cluster — CrashLoopBackOff, AerospikeCluster CRD phase=Error / WaitingForMigration / InProgress stuck, ConfigDegraded, circuit breaker active, split cluster, ACLSyncError, webhook rejection — or any troubleshooting flow that resolves to running diagnostic commands or queries against an ACKO Aerospike cluster. Triggers on: 'CrashLoopBackOff', 'phase=Error', 'reconcile failure', 'cluster won''t start', 'pods stuck', 'migration stuck', 'dynamic config failed', 'CE 8.1 config error', 'AerospikeCluster reconcile', 'debug aerospike cluster', 'troubleshoot ACKO', 'split cluster', 'ACLSyncError', 'webhook rejection', 'circuit breaker active', 'ConfigDegraded'."
---

# ACKO Cluster Debugging Procedure

The systematic procedure for a broken ACKO-managed Aerospike CE cluster: (1) the 6-step ordering Aerospike SREs use during real outages, (2) CE 8.1 config pitfalls that surface as cryptic boot failures, (3) a remediation matrix mapping symptoms to fixes. Full command blocks for every step: [`./reference/playbook.md`](./reference/playbook.md). For routine reads the CLI is self-describing (`ackoctl <noun> --help`) — load this skill when something is actually broken.

## Tool routing — ackoctl first, kubectl fallback

Prefer `ackoctl` for **both** planes — it goes through cluster-manager, the authoritative source for AerospikeCluster state (normalises CR status, classifies K8s events, enforces workspace ACL). Data plane: `ackoctl cluster info` / `info --command=...` / `query exec` / `record get` / `set list`. K8s plane: `ackoctl k8s cluster list / get / reconcile / scale / logs / events` (requires cluster-manager `K8S_MANAGEMENT_ENABLED=true`; on 404, use `kubectl`). Fall back to `kubectl` / direct `asinfo` only when `ackoctl` is unavailable or a field isn't surfaced yet.

## Cluster selection & mutation safety

Map the user's wording ("in dev", "prod-us") to an ackoctl context via `--context=<name>`; if ambiguous, list `ackoctl config view -o yaml` and ask (`{ctx}` = resolved context). **Confirm with the user before any state-mutating call** — `record put`/`delete`, `cluster configure-namespace`, `info --allow-write` (`set-config:`/`recluster:`), `index create`/`delete`, `k8s cluster scale`/`reconcile`, `udf upload`/`remove`, `admin user/role *`, `connection delete` (cascades attached notes). Prefer the no-side-effect read verbs for diagnosis: `k8s cluster get`, `info` (no `--allow-write`), `query exec`, `record get`.

If `ackoctl` is not installed or no context is configured, tell the user: install via `curl -fsSL https://raw.githubusercontent.com/aerospike-ce-ecosystem/ackoctl/main/install.sh | sh`, then `ackoctl config set-context <name> --server=<url> --token=<jwt> --workspace-id=<ws>`; kubectl-only diagnosis can proceed meanwhile (data-plane probes go through `kubectl exec` instead). The `ackoctl` skill covers install and configuration in full.

## Debugging procedure

Execute in order; stop and report as soon as the root cause is identified. Command blocks per step: [`./reference/playbook.md`](./reference/playbook.md).

1. **Gather cluster overview** — pick/confirm a `CONN_ID` (`ackoctl connection list`); data plane via `ackoctl cluster info` + `info --command='statistics'|'status'`; K8s plane via `ackoctl k8s cluster get <ns>/<name> -o yaml` (phase, size, conditions, migration in one payload) and `k8s cluster events`.
2. **Branch on `status.phase`:**
   - `Error` → read `status.lastReconcileError` + recent events: config parse errors, image pull, quota, webhook failures. (The circuit breaker surfaces as `BackoffActive`, not `Error`.)
   - `BackoffActive` → inspect `ReconcileHealthy`. `True` = transient, auto-retries (backoff capped 5 min). `False/PermanentError` = validation/configgen/Secret error, **no retry**: fix root cause, then toggle `paused: true → null` or edit spec.
   - `ACLSync` (stuck) → ACL sync failing; cluster will NOT reach `Completed` (requeues ~30s). Check `ACLSynced` condition, `ACLSyncError` event, password Secret.
   - `WaitingForMigration` → usually normal during scale-down; report `migrationStatus.remainingPartitions`, advise waiting.
   - `InProgress` stuck >5 min → pods/PVCs/describe/operator logs: Pending PVC, ImagePullBackOff, scheduling failure.
   - `Completed` but user reports issues → data-plane probes (`info`, `query exec` sampling); check split cluster (`cluster_size` mismatch), stop-writes, `proto-fd-max` exhaustion.
   - `ConfigDegraded` → 2PC dynamic config apply AND LIFO rollback both failed; pods hold divergent runtime configs and the operator **halts reconciliation** (`ConfigDegradedSkip` Warning, ~60s requeue). **Do not** flip `enableDynamicConfigUpdate` or re-apply. Recovery is manual: revert `spec.aerospikeConfig` to last-known-good, then cold-restart pods / reset the phase; done when `phase=Completed` and `DynamicConfigDegraded` clears (`DynamicConfigRecovered`). Diagnose via `DynamicConfigDegraded` + `status.pods[*].dynamicConfigChanges`.
3. **Pod-level issues** — logs (`--previous` for CrashLoopBackOff) via `ackoctl k8s cluster logs` or kubectl. CrashLoopBackOff → config parse error (removed 7.x params), OOM, `data-size` < 512 MiB; ImagePullBackOff → image/pull-secret; Pending → resources/PVC.
4. **Operator logs** — `kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=200`: reconcile errors, webhook rejections, resource-creation failures.
5. **Events timeline** — `ackoctl k8s cluster events` (classified) or raw kubectl events. Key reasons: `CircuitBreakerActive` (→ `BackoffActive`, `acko_circuit_breaker_active=1`), `RestartFailed`, `ScaleDownDeferred`, `DynamicConfigStatusFailed`, `ACLSyncError`, `ConfigDegradedSkip`, `TemplateResolutionError`, `ReadinessGateBlocking`.
6. **Dynamic config status** — `status.pods[].dynamicConfigStatus`; `Failed` = parameter not dynamic → advise `enableDynamicConfigUpdate: false` for a rolling restart.

## Remediation actions

Phase-keyed fixes (`BackoffActive`, `ConfigDegraded`, `ACLSync`, dynamic-config `Failed`) are in the step-2 branches above. Additionally:

| Issue | Remediation |
|-------|-------------|
| Config parse error | Fix `aerospikeConfig` in CR and re-apply |
| Image pull failure | Fix image name or add imagePullSecret |
| PVC Pending | Check StorageClass exists and has capacity |
| Resource insufficient | Reduce resource requests or add nodes to K8s cluster |
| CE constraint violation | Fix CR to comply (size ≤ 8, namespaces ≤ 2, no xdr/tls, CE image ≥ ce-8) |
| Split cluster | Verify network connectivity, check `cluster-name` consistency. Compare `status.aerospikeClusterSize` with `status.size` |
| Stop writes | Increase storage capacity or reduce data volume |
| On-demand op `Error` | Unknown `kind` or `podList` names no existing pod → fix/clear: `kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"operations":null}}'` |

## CE 8.1 common pitfalls

CrashLoopBackOff on a CE 8.1 config almost always traces to one of: `info { port }` block (removed — use `admin { port 3008 }`), `memory-size` (use `storage-engine memory { data-size N }`), `write-block-size` (use `flush-size`), `data-size` < 536870912 (512 MiB), `nsup-period=0` with `default-ttl!=0`, or byte values as strings (must be integer bytes). Full table: `acko-config-reference/reference/breaking-changes-7x-to-8.md`.

Report the root cause with the command output that proves it, then the remediation commands.
