---
name: acko-operations
description: "MUST USE for any modification, debugging, or management of existing Aerospike Kubernetes clusters. Contains ACKO-specific procedures, kubectl commands, and troubleshooting decision trees that prevent data loss during operations. Without this skill, common operations like scaling and upgrades risk incorrect spec patches, webhook rejections, or missed warm restart procedures. Triggers on: scale up/down Aerospike cluster, rolling upgrade, dynamic config change (proto-fd-max, transaction-threads), warm/cold restart, ACL user management, pause/resume, clone cluster, clear operations, migration status, CrashLoopBackOff debugging, phase=Error troubleshooting, asinfo commands, cluster status checks. Covers all ACKO Day-2 operations with verified step-by-step procedures."
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

## 3. Dynamic Config Update (No Restart)

Apply configuration changes without restarting pods. Only works for dynamically changeable parameters.

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
- `high-water-memory-pct` (CE 7.x; replaced in 8.1)
- `evict-used-pct`
- `evict-tenths-pct`
- `nsup-period`

### Step 3: Verify

```bash
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq '.[].dynamicConfigStatus'
```

- `Applied`: Change applied successfully (no restart needed).
- `Failed`: Parameter is not dynamically changeable. Set `enableDynamicConfigUpdate: false` to force a rolling restart.
- `Pending`: Change is being applied.

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

## 14. Troubleshooting Decision Tree

Use this decision tree to diagnose cluster issues systematically.

### Phase = Error

```
1. Get the error message:
   kubectl get asc <name> -n <ns> -o jsonpath='{.status.lastReconcileError}'

2. Check events for details:
   kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp'

3. Common causes:
   - Invalid aerospikeConfig (parse error) -> Fix config and re-apply
   - Image pull failure -> Check image name, registry access, imagePullSecrets
   - Resource quota exceeded -> Increase quota or reduce resource requests
   - Webhook rejection -> Check CE constraints (see acko-deploy skill)

4. After fixing: the operator auto-retries reconciliation.
```

### Phase = WaitingForMigration

```
1. This is NORMAL during scale-down. The operator waits for data migration to finish.

2. Check migration progress:
   kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep migrate

3. If migrate_partitions_remaining = 0, migration is complete.

4. The operator auto-proceeds after migration completes. No manual action needed.
```

### Phase = InProgress (Stuck for > 5 Minutes)

```
1. Check for pending PVCs:
   kubectl get pvc -n <ns> -l aerospike.io/cr-name=<name>
   -> If PVC is Pending: check StorageClass, available capacity

2. Check for image pull issues:
   kubectl describe pod <pod> -n <ns> | grep -A5 "Events:"

3. Check for scheduling failures:
   kubectl get pods -n <ns> -l aerospike.io/cr-name=<name> -o wide
   kubectl describe pod <pending-pod> -n <ns>

4. Check operator logs:
   kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=200
```

### Pod CrashLoopBackOff

```
1. Check the Aerospike server logs from the crashed container:
   kubectl -n <ns> logs <pod> -c aerospike-server --previous

2. Common causes:
   - Config parse error (e.g., using removed 'info' port block in 8.1)
   - data-size too small (minimum 512 MiB)
   - nsup-period=0 with non-zero default-ttl
   - Memory limit too low for configured data-size

3. Fix the aerospikeConfig in the CR and re-apply.
```

### CircuitBreakerActive Event

```
1. Check failure count (threshold: 10 consecutive failures):
   kubectl get asc <name> -n <ns> -o jsonpath='{.status.failedReconcileCount}'

2. Check the last error:
   kubectl get asc <name> -n <ns> -o jsonpath='{.status.lastReconcileError}'

3. Fix the root cause. The operator auto-retries with exponential backoff:
   delay = min(2^n, 300) seconds

4. After a successful reconciliation, CircuitBreakerReset event is emitted.
```

### Webhook Rejects CR (Apply Error)

```
1. Read the error message from kubectl apply output.

2. Common CE constraint violations:
   - size > 8
   - namespaces > 2
   - Enterprise image (contains 'enterprise', 'ee-', or 'ent-')
   - xdr or tls section present
   - heartbeat.mode != mesh
   - Missing admin user with sys-admin + user-admin roles

3. See reference/validation-rules.md for the complete list of 53 errors and 15 warnings.
```

### dynamicConfigStatus = Failed

```
1. Check which pods failed:
   kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq '.[].dynamicConfigStatus'

2. The parameter you changed is not dynamically changeable.

3. Fix: set enableDynamicConfigUpdate to false to force a rolling restart:
   kubectl patch asc <name> -n <ns> --type=merge \
     -p '{"spec":{"enableDynamicConfigUpdate":false}}'
```

### ReadinessGateBlocking Event

```
1. Check pod conditions:
   kubectl get pod <pod> -o jsonpath='{.status.conditions}' | jq '.[]'

2. The readiness gate acko.io/aerospike-ready is not satisfied.

3. Check if Aerospike is actually running and healthy inside the pod:
   kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v status
```

---

## 15. Diagnostic Commands Quick Reference

Detail: `./reference/diagnostic-commands.md`

---

## Reference Documents

- [Operations Reference](./reference/operations.md) -- Detailed Day-2 operations with all kubectl commands
- [Events Reference](./reference/events.md) -- All 37 Kubernetes events emitted by ACKO
- [Troubleshooting Reference](./reference/troubleshooting.md) -- Symptom-based diagnostic table with commands
- [Validation Rules Reference](./reference/validation-rules.md) -- 53 webhook errors + 15 warnings
