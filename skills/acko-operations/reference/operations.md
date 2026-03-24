# Day-2 Operations Reference

Complete reference for all ACKO Day-2 operations with kubectl commands and expected behaviors.

---

## 1. Scaling

### Scale Up

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"size":5}}'
```

Phase: `ScalingUp` -> `Completed`. CE maximum: 8 nodes.

### Scale Down

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"size":3}}'
```

Phase: `ScalingDown` -> (`WaitingForMigration`) -> `Completed`.

If data migration is in progress, scale-down is automatically deferred. The operator retries automatically after migration completes.

### Batch Size

```yaml
spec:
  rackConfig:
    scaleDownBatchSize: "1"       # 1 pod per rack at a time
    maxIgnorablePods: 1           # Allow 1 stuck pod without blocking
```

---

## 2. Rolling Update

### Image Upgrade

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"image":"aerospike:ce-8.1.1.1"}}'
```

Phase: `RollingRestart` -> `Completed`.

### Static Config Change (Restart Required)

```bash
kubectl patch asc <name> -n <ns> --type=merge \
  -p '{"spec":{"aerospikeConfig":{"service":{"proto-fd-max":20000}}}}'
```

Phase: `RollingRestart` -> `Completed`.

### Dynamic Config Change (No Restart)

```yaml
spec:
  enableDynamicConfigUpdate: true
  aerospikeConfig:
    service:
      proto-fd-max: 20000               # Dynamic parameter
    namespaces:
      - name: test
        high-water-memory-pct: 70       # Dynamic parameter (CE 7.x)
        stop-writes-pct: 90             # Dynamic parameter (CE 7.x)
```

Verification:
```bash
kubectl get asc <name> -o jsonpath='{.status.pods}' | jq '.[].dynamicConfigStatus'
```

Status values:
- `Applied`: Success (no restart needed)
- `Failed`: Parameter is not dynamically changeable; set `enableDynamicConfigUpdate: false` to force rolling restart
- `Pending`: Change is being applied

### Batch Size

```yaml
spec:
  rollingUpdateBatchSize: 1             # Global (integer or "25%")
  rackConfig:
    rollingUpdateBatchSize: "50%"       # Per-rack override
```

---

## 3. On-Demand Restart

Only one operation at a time. Remove from spec after completion.

### WarmRestart (SIGUSR1)

```yaml
spec:
  operations:
    - kind: WarmRestart
      id: warm-001                      # 1-20 chars, unique
      # podList: [...]                  # Optional: specific pods
```

### PodRestart (Cold)

```yaml
spec:
  operations:
    - kind: PodRestart
      id: cold-001
      podList:
        - <cluster>-0-2                # Optional: specific pods
```

### Status Check and Cleanup

```bash
kubectl get asc <name> -o jsonpath='{.status.operationStatus}' | jq .
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"operations":null}}'
```

---

## 4. ACL Management

### Add User

```bash
kubectl create secret generic new-user-secret -n <ns> --from-literal=password=<pw>
kubectl patch asc <name> -n <ns> --type=json \
  -p '[{"op":"add","path":"/spec/aerospikeAccessControl/users/-","value":{"name":"new-user","roles":["reader"],"secretName":"new-user-secret"}}]'
```

### Change Password

```bash
kubectl create secret generic <secret> -n <ns> --from-literal=password=<new-pw> --dry-run=client -o yaml | kubectl apply -f -
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"operations":[{"kind":"WarmRestart","id":"pw-change-001"}]}}'
```

### Valid Privileges

`read`, `write`, `read-write`, `read-write-udf`, `sys-admin`, `user-admin`, `data-admin`, `truncate`

Format: `"<code>"` / `"<code>.<namespace>"` / `"<code>.<namespace>.<set>"`

---

## 5. Template Operations

### Resync

```bash
kubectl annotate asc <name> -n <ns> acko.io/resync-template=true
```

The annotation is automatically removed after resync completes.

### Sync Status

```bash
kubectl get asc <name> -o jsonpath='{.status.templateSnapshot.synced}'   # true/false
kubectl get events -n <ns> --field-selector reason=TemplateDrifted
```

---

## 6. Pause / Resume

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"paused":true}}'    # Pause
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"paused":null}}'     # Resume
```

---

## 7. Readiness Gate

```yaml
spec:
  podSpec:
    readinessGateEnabled: true        # Triggers rolling restart when toggled
```

```bash
kubectl get pod <pod> -o jsonpath='{.status.conditions}' | jq '.[] | select(.type=="acko.io/aerospike-ready")'
```

---

## 8. Network

### Access Type

```yaml
spec:
  aerospikeNetworkPolicy:
    accessType: pod                   # pod | hostInternal | hostExternal | configuredIP
```

### LoadBalancer

```yaml
spec:
  seedsFinderServices:
    loadBalancer:
      port: 3000
      annotations:
        service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
```

### NetworkPolicy

```yaml
spec:
  networkPolicyConfig:
    enabled: true
    type: kubernetes                  # kubernetes | cilium
```

---

## 9. PDB / Maintenance

```yaml
spec:
  disablePDB: false                   # PDB enabled (default)
  maxUnavailable: 1                   # Integer or "25%"
  k8sNodeBlockList:
    - node-to-drain-01                # Block scheduling before draining
```

---

## 10. Recovery

### Circuit Breaker

```bash
kubectl get asc <name> -o jsonpath='{.status.failedReconcileCount}'       # Threshold: 10
kubectl get asc <name> -o jsonpath='{.status.lastReconcileError}'
```

Fix root cause. Operator auto-retries with backoff: `min(2^n, 300)` seconds.

### WaitingForMigration

```bash
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep migrate
```

Wait for completion. Operator auto-proceeds.

### InProgress Stuck

```bash
kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp'
kubectl get pvc -n <ns> -l aerospike.io/cr-name=<name>
kubectl -n aerospike-operator logs -l control-plane=controller-manager --tail=100
```

---

## 11. Migration Status

The operator tracks data migration at both cluster and pod level:

```bash
# Cluster-level migration status
kubectl get asc <name> -n <ns> -o jsonpath='{.status.migrationStatus}' | jq .
# Output: {"inProgress": true, "remainingPartitions": 1024, "lastChecked": "2026-03-24T..."}

# Per-pod migration partitions
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq 'to_entries[] | {pod: .key, migrating: .value.migratingPartitions}'
```

The operator defers destructive actions (scale-down, pod removal) until `migrationStatus.inProgress` is `false`.

---

## 12. Cluster Deletion

```bash
kubectl delete asc <name> -n <ns>
```

Sequence:
1. `ClusterDeletionStarted` event -> Phase `Deleting`
2. `cascadeDelete: true`: PVCs automatically deleted
3. `cascadeDelete: false`: PVCs retained; manual cleanup: `kubectl delete pvc -n <ns> -l aerospike.io/cr-name=<name>`
4. `FinalizerRemoved` event -> CR deleted
