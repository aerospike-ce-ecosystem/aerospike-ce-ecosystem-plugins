---
name: acko-operations
description: "MUST USE for any modification, debugging, or management of existing Aerospike Kubernetes clusters. Contains ACKO-specific procedures, kubectl commands, and troubleshooting decision trees that prevent data loss during operations. Without this skill, common operations like scaling and upgrades risk incorrect spec patches, webhook rejections, or missed warm restart procedures. Triggers on: scale up/down Aerospike cluster, rolling upgrade, dynamic config change (proto-fd-max, transaction-threads, 2PC rollout), ConfigDegraded phase, circuit breaker / permanent error, warm/cold restart, ACL user management, pause/resume, clone cluster, clear operations, migration status, asinfo commands, cluster status checks. For symptom-driven debugging (CrashLoopBackOff, phase=Error, reconcile failure), use acko-debugging instead."
---

# ACKO Day-2 Operations & Troubleshooting

Step-by-step procedures for managing and debugging Aerospike CE clusters on Kubernetes after initial deployment.

---

## 1. Scale Up / Scale Down

### Scale Up

Increase `spec.size` to add nodes. CE maximum is 8.

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"size":5}}'
```

**Phase progression**: `ScalingUp` -> `Completed`

**Verification**:
```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phase}'
kubectl get pods -n <ns> -l aerospike.io/cr-name=<name>
kubectl get asc <name> -n <ns> -o jsonpath='{.status.size}'
```

### Scale Down

Decrease `spec.size` to remove nodes. The operator waits for data migration to complete before removing pods.

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"size":3}}'
```

**Phase progression**: `ScalingDown` -> (`WaitingForMigration`) -> `Completed`

If migration is in progress, scale-down is automatically deferred and retried after migration completes.

**Verification**:
```bash
# Check migration status (cluster-level)
kubectl get asc <name> -n <ns> -o jsonpath='{.status.migrationStatus}' | jq .
# Per-node migration partitions
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq '.[].migratingPartitions'
# Direct asinfo check
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep migrate
```

### Batch Size for Scaling

Control how many pods are added/removed per batch per rack:

```yaml
spec:
  rackConfig:
    scaleDownBatchSize: "1"         # 1 pod per rack at a time
    maxIgnorablePods: 1             # Allow 1 stuck pod without blocking
```

---

## 2. Image Upgrade (Rolling Restart)

Change the Aerospike image to trigger a rolling restart of all pods.

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"image":"aerospike:ce-8.1.1.1"}}'
```

**Phase progression**: `RollingRestart` -> `Completed`

**Control the batch size**:
```yaml
spec:
  rollingUpdateBatchSize: 1           # Global: restart N pods per batch (integer or "25%")
  rackConfig:
    rollingUpdateBatchSize: "50%"     # Per-rack override
```

**Verification**:
```bash
kubectl get asc <name> -n <ns> -w
kubectl get pods -n <ns> -l aerospike.io/cr-name=<name> -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'
```

---

## 3. Dynamic Config Update (No Restart, 2-Phase Commit)

Apply configuration changes without restarting pods. Only works for dynamically changeable parameters.

### How the operator applies changes (2PC — April 2026)

1. **Phase 1 — validate-all**: operator probes every pod with the proposed change. If ANY pod rejects validation (syntax, node unresponsive), the entire update is aborted and no pod is mutated.
2. **Phase 2 — apply sequentially**: each pod is updated with a per-pod 30 s timeout (independent of the reconciliation timeout).
3. **On apply failure**: a LIFO rollback runs across pods that were already updated. Each rollback also has the per-pod 30 s budget.
4. **On rollback failure**: cluster transitions to `phase = ConfigDegraded`, `ConditionDynamicConfigDegraded=True` is set, and reconciliation **halts** (`ConfigDegradedSkip` Warning every ~60s) until you intervene.

This makes dynamic config rollouts atomic from the user's perspective: either every pod ends up on the new value, every pod ends up back on the old value, or you observe `ConfigDegraded` and intervene manually (revert the value, cold-restart / reset the phase).

### Step 1: Enable Dynamic Config

```yaml
spec:
  enableDynamicConfigUpdate: true
```

### Step 2: Patch the Config

```bash
kubectl patch asc <name> -n <ns> --type=merge \
  -p '{"spec":{"aerospikeConfig":{"service":{"proto-fd-max":20000}}}}'
```

### Dynamically Changeable Parameters (Common)

- `proto-fd-max`
- `max-record-size`
- `stop-writes-sys-memory-pct`
- `evict-used-pct`
- `evict-tenths-pct`
- `nsup-period`

### Step 3: Verify

```bash
# Per-pod, per-path tracking (April 2026)
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' | jq

# Aggregate per-pod status (legacy field, still populated)
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq '.[].dynamicConfigStatus'
```

Per-change `result` enum (in `dynamicConfigChanges`): `Applied`, `Failed`, `Pending`, `RolledBack`, `RollbackFailed`.

Top-level statuses:
- `Applied`: Change applied successfully (no restart needed).
- `Failed`: Phase 1 validation rejected the change on at least one pod, OR phase 2 apply failed and rollback succeeded. Set `enableDynamicConfigUpdate: false` to force a rolling restart.
- `Pending`: Change is being applied.

**Removing** a config key always forces a rolling restart (even for a dynamic param) — reverting to the server default cannot be expressed as `set-config`.

### When apply AND rollback both fail

You will see `phase = ConfigDegraded` and reconciliation halts (`ConfigDegradedSkip` Warning events every ~60s). Do NOT try to "fix" it by toggling `enableDynamicConfigUpdate` — revert the offending value in the spec, then cold-restart the pods / reset the phase so reconciliation resumes. See the `acko-debugging` skill for the full recovery flow.

### Static Config Change (Requires Restart)

If `enableDynamicConfigUpdate` is `false` (default), any config change triggers a rolling restart:

```bash
kubectl patch asc <name> -n <ns> --type=merge \
  -p '{"spec":{"aerospikeConfig":{"service":{"proto-fd-max":20000}}}}'
```

**Phase progression**: `RollingRestart` -> `Completed`

---

## 4. Warm Restart / Cold Restart

On-demand restart of pods. Only one operation at a time. Remove the operation from spec after completion.

**Constraints (webhook-enforced):**
- `kind` must be one of `WarmRestart` (SIGUSR1) or `PodRestart` (delete + recreate). No other values are accepted.
- `id` must be 1–20 characters, unique-per-cluster.
- The operations list cannot be modified (including changing `podList`) while an operation has `status.operation.phase = InProgress` — wait for it to complete (or fail) before queueing another.

**Controller semantics:** the op terminates as `phase=Error` (not silent Completed) on an unknown `kind` or when `podList` names no existing pod. Batches gate on the readiness-gate / migration guard like rolling restarts, so a batch may legitimately pause.

### Warm Restart (SIGUSR1)

Sends SIGUSR1 to the Aerospike server process. Faster than a cold restart; preserves in-memory state where possible.

```yaml
spec:
  operations:
    - kind: WarmRestart
      id: warm-001               # Unique ID, 1-20 characters
      # podList: ["<cluster>-0-0"]  # Optional: specific pods only
```

### Cold Restart (Pod Delete + Recreate)

Deletes and recreates the pod. Full process restart.

```yaml
spec:
  operations:
    - kind: PodRestart
      id: cold-001
      podList:                    # Optional: omit to restart all pods
        - <cluster>-0-2
```

### Check Operation Status

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.operationStatus}' | jq .
```

### Clean Up After Completion

Remove the operation from spec after it completes:

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"operations":null}}'
```

**Important**: Do not add a new operation while one is `InProgress`. The webhook rejects it with: `"cannot change operations while operation \"ID\" is InProgress"`.

---

## 5. ACL Management

### Add a New User

```bash
# Step 1: Create the K8s Secret for the new user's password
kubectl create secret generic new-user-secret -n <ns> --from-literal=password=<pw>

# Step 2: Add the user to the CR
kubectl patch asc <name> -n <ns> --type=json \
  -p '[{"op":"add","path":"/spec/aerospikeAccessControl/users/-","value":{"name":"new-user","roles":["reader"],"secretName":"new-user-secret"}}]'
```

### Change a User's Password

```bash
# Step 1: Update the K8s Secret
kubectl create secret generic <secret-name> -n <ns> \
  --from-literal=password=<new-pw> --dry-run=client -o yaml | kubectl apply -f -

# Step 2: Trigger a warm restart to pick up the new password
kubectl patch asc <name> -n <ns> --type=merge \
  -p '{"spec":{"operations":[{"kind":"WarmRestart","id":"pw-change-001"}]}}'
```

### Add a Custom Role

```bash
kubectl patch asc <name> -n <ns> --type=json \
  -p '[{"op":"add","path":"/spec/aerospikeAccessControl/roles/-","value":{"name":"app-reader","privileges":["read.testns"]}}]'
```

### Valid Privilege Codes

`read`, `write`, `read-write`, `read-write-udf`, `sys-admin`, `user-admin`, `data-admin`, `truncate`

Privilege format: `"<code>"` or `"<code>.<namespace>"` or `"<code>.<namespace>.<set>"`

### ACL Requirements

- At least one user must have BOTH `sys-admin` and `user-admin` roles.
- Every user must have a `secretName` pointing to a K8s Secret with a `password` key.
- User names and role names must be unique.

---

## 6. Pause / Resume Reconciliation

### Pause

Stop the operator from reconciling this cluster. Existing pods continue running.

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"paused":true}}'
```

**Phase**: `Paused`

### Resume

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"paused":null}}'
```

**Phase**: `Paused` -> `InProgress` -> `Completed`

On resume, the operator clears stale `status.failedReconcileCount` and `status.lastReconcileError`. This is the recommended way to clear a stuck circuit breaker after fixing a permanent error (see the `acko-debugging` skill).

### Pause/Resume Metrics

| Metric | Type | Meaning |
|--------|------|---------|
| `acko_cluster_paused_timestamp_seconds` | gauge | Unix timestamp when pause began (`0` if not paused) |
| `acko_cluster_paused_duration_seconds` | histogram | Distribution of pause-cycle durations (observed on resume) |
| `acko_circuit_breaker_active` | gauge | `1` while the breaker is tripped, `0` otherwise |

Pause duration is computed from the `ReconciliationPaused` condition's `lastTransitionTime`. Full metric catalog: `./reference/metrics.md`.

---

## 7. Delete Cluster

```bash
kubectl delete asc <name> -n <ns>
```

**Deletion sequence**:
1. `ClusterDeletionStarted` event -> Phase `Deleting`
2. If `cascadeDelete: true` on volumes: PVCs are automatically deleted.
3. If `cascadeDelete: false`: PVCs are retained. Clean up manually:
   ```bash
   kubectl delete pvc -n <ns> -l aerospike.io/cr-name=<name>
   ```
4. `FinalizerRemoved` event -> CR is deleted.

---

## 8. Template Resync

If you modified an `AerospikeClusterTemplate` and want existing clusters to pick up changes:

```bash
kubectl annotate asc <name> -n <ns> acko.io/resync-template=true
```

The annotation is automatically removed after resync completes.

**Check sync status**:
```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.templateSnapshot.synced}'
kubectl get events -n <ns> --field-selector reason=TemplateDrifted
```

---

## 9. Clone Cluster

Create a copy of an existing cluster with a new name (via aerospike-cluster-manager API or manually):

```bash
# Manual clone: export existing CR, strip status/operations, change name
kubectl get asc <source> -n <ns> -o json | \
  jq 'del(.status, .metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .spec.operations, .spec.paused) | .metadata.name = "<new-name>"' | \
  kubectl apply -f -
```

The clone preserves the full spec (aerospikeConfig, storage, monitoring, ACL) but strips `operations` and `paused` fields.

---

## 10. Clear Stuck Operations

If an operation is stuck in `InProgress` and blocking new operations:

```bash
# Remove operations from spec to unblock
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"operations":null}}'
```

Via aerospike-cluster-manager API: `DELETE /api/k8s/clusters/{namespace}/{name}/operations`

---

## 11. Network Configuration

Detail: `./reference/operations.md` (Section 8: Network)

---

## 12. PDB and Maintenance

Detail: `./reference/operations.md` (Section 9: PDB / Maintenance)

---

## 13. Readiness Gate

Detail: `./reference/operations.md` (Section 7: Readiness Gate)

---

## 14. Troubleshooting

For systematic outage diagnosis (`phase=Error`, stuck migrations, `CrashLoopBackOff`, `CircuitBreakerActive`, `ConfigDegraded`, `ReadinessGateBlocking`, webhook rejection, `dynamicConfigStatus=Failed`, paused reconciliation), use the dedicated **`acko-debugging` skill** — it carries the 6-step procedure, CE 8.1 pitfalls, and remediation matrix that used to live here.

`reference/troubleshooting.md` and `reference/validation-rules.md` (kept in this skill) remain the canonical symptom-→command and webhook-error catalogs that `acko-debugging` cross-links into.

---

## 15. Diagnostic Commands Quick Reference

Detail: `./reference/diagnostic-commands.md`

---

## 16. OpenTelemetry Observability

The operator can export its **reconcile traces, metrics, and logs** to an OTLP/gRPC collector — off by default. Enable it on a running cluster with a Helm upgrade (no CR change):

```bash
helm upgrade acko oci://ghcr.io/aerospike-ce-ecosystem/charts/aerospike-ce-kubernetes-operator \
  -n aerospike-operator --reuse-values \
  --set observability.otel.enabled=true \
  --set observability.otel.endpoint=otel-collector.observability.svc.cluster.local:4317
```

The Deployment rolls; the new pod logs `OpenTelemetry export enabled`. Confirm export is flowing — a blocked egress instead logs `missing address` / `context deadline exceeded`:

```bash
kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=50 | grep -iE 'otel|export'
```

The collector then receives reconcile spans (`Reconcile` → `reconcileCluster` → `reconcileRacks`), the `acko_*` + controller-runtime metrics, and operator logs. Disable again with `--set observability.otel.enabled=false`.

Config rules — `enabled` + `endpoint` both required, OTLP/gRPC endpoint scheme, the auto-added NetworkPolicy egress (`observability.otel.collectorPort`) — are covered in **acko-deploy**.

---

## Reference Documents

- [Operations Reference](./reference/operations.md) -- Detailed Day-2 operations with all kubectl commands
- [Events Reference](./reference/events.md) -- Kubernetes events emitted by ACKO (including 2PC dynamic-config events)
- [Troubleshooting Reference](./reference/troubleshooting.md) -- Symptom-based diagnostic table with commands
- [Validation Rules Reference](./reference/validation-rules.md) -- Webhook error/warning catalog (canonical source)
- [Diagnostic Commands](./reference/diagnostic-commands.md) -- kubectl one-liners for common diagnostics
- [Operator Metrics](./reference/metrics.md) -- Prometheus metrics emitted by the operator
