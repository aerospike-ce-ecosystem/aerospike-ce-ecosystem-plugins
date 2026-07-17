---
name: acko-operations
description: "MUST USE for any modification, debugging, or management of existing Aerospike Kubernetes clusters. Contains ACKO-specific procedures, kubectl commands, and troubleshooting decision trees that prevent data loss during operations. Without this skill, common operations like scaling and upgrades risk incorrect spec patches, webhook rejections, or missed warm restart procedures. Triggers on: scale up/down Aerospike cluster, rolling upgrade, dynamic config change (proto-fd-max, transaction-threads, 2PC rollout), ConfigDegraded phase, circuit breaker / permanent error, warm/cold restart, ACL user management, pause/resume, clone cluster, clear operations, migration status, asinfo commands, cluster status checks. For symptom-driven debugging (CrashLoopBackOff, phase=Error, reconcile failure), use acko-debugging instead."
---

# ACKO Day-2 Operations & Troubleshooting

Procedures for managing Aerospike CE clusters on Kubernetes after initial deployment. Every section here is the decision core; full kubectl detail per operation lives in [`./reference/operations.md`](./reference/operations.md) (section numbers below refer to it).

---

## 1. Scale Up / Scale Down (ops ref §1)

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"size":5}}'
```

- Up: `ScalingUp` → `Completed`. CE max is 8.
- Down: `ScalingDown` → (`WaitingForMigration`) → `Completed`. The operator waits for data migration before removing pods and auto-retries after it drains. Verify with `kubectl get asc <name> -o jsonpath='{.status.migrationStatus}' | jq .`
- Batching: `rackConfig.scaleDownBatchSize` (per rack), `rackConfig.maxIgnorablePods` (explicit `0`/`"0%"` = ignore none — honored strictly).

## 2. Image Upgrade / Rolling Restart (ops ref §2)

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"image":"aerospike:ce-8.1.1.1"}}'
```

`RollingRestart` → `Completed`. Batch control: `spec.rollingUpdateBatchSize` (int or `"25%"`), per-rack override `rackConfig.rollingUpdateBatchSize`. Besides image/static config, editing `spec.podService` or `spec.aerospikeNetworkPolicy` also rolls pods (pod-spec hash).

## 3. Dynamic Config Update — 2-Phase Commit (ops ref §2)

Set `spec.enableDynamicConfigUpdate: true`, then patch the config value. The operator runs a 2PC rollout: **validate-all** (any pod rejects → whole update aborted, nothing mutated) → **apply sequentially** (per-pod 30s timeout) → on apply failure, **LIFO rollback**. Net effect: all pods on the new value, all pods back on the old value, or `phase=ConfigDegraded`.

- Verify: `kubectl get asc <name> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' | jq` (`result`: `Applied`/`Failed`/`Pending`/`RolledBack`/`RollbackFailed`).
- `Failed` = phase-1 rejection or apply-failed-rollback-succeeded → set `enableDynamicConfigUpdate: false` to force a rolling restart instead.
- **Removing** a key always forces a rolling restart (revert-to-default is not expressible as `set-config`). `replication-factor` (and legacy `memory-size`) are never dynamic — they cold-restart.
- **ConfigDegraded** (apply AND rollback both failed): reconciliation **halts** with `ConfigDegradedSkip` Warning events (~60s requeue) until you intervene — revert the offending value, then cold-restart pods / reset the phase. Do NOT toggle `enableDynamicConfigUpdate`. Full recovery flow: `acko-debugging` skill.

Common dynamic params: `proto-fd-max`, `max-record-size`, `stop-writes-sys-memory-pct`, `evict-used-pct`, `evict-tenths-pct`, `nsup-period`.

## 4. Warm / Cold Restart — spec.operations (ops ref §3)

```yaml
spec:
  operations:
    - kind: WarmRestart        # SIGUSR1; or PodRestart (delete + recreate)
      id: warm-001             # 1-20 chars, unique
      # podList: ["<cluster>-0-0"]   # optional: specific pods
```

Webhook-enforced: `kind` ∈ {`WarmRestart`, `PodRestart`}; one operation at a time; the list (incl. `podList`) cannot change while one is `InProgress` (`"cannot change operations while operation \"ID\" is InProgress"`). Controller: op ends `phase=Error` on unknown kind / nonexistent pod; batches gate on the readiness/migration guard and honor `rackConfig.rollingUpdateBatchSize`. Check `status.operationStatus`; clean up (or unstick — §10) with:

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"operations":null}}'
```

## 5. ACL Management (ops ref §4)

- **Add user**: create the password Secret, then JSON-patch the user into `spec.aerospikeAccessControl.users` (`{"name":...,"roles":[...],"secretName":...}`).
- **Change password**: update the Secret in place, then trigger a `WarmRestart` operation to pick it up.
- Requirements: ≥1 user with BOTH `sys-admin` + `user-admin`; every user has `secretName` (Secret key `password`); unique user/role names. Privilege codes: `read`, `write`, `read-write`, `read-write-udf`, `sys-admin`, `user-admin`, `data-admin`, `truncate` — format `"<code>[.<namespace>[.<set>]]"` (admin codes are global-only).

## 6. Pause / Resume (ops ref §6)

```bash
kubectl patch asc <name> -n <ns> --type=merge -p '{"spec":{"paused":true}}'   # pause; null to resume
```

Resume clears stale `failedReconcileCount`/`lastReconcileError` — the recommended way to unstick a tripped circuit breaker after fixing a permanent error. Pause/breaker metrics: `./reference/metrics.md`.

## 7. Delete Cluster (ops ref §12)

`kubectl delete asc <name> -n <ns>` → `ClusterDeletionStarted` → `Deleting` → `FinalizerRemoved`. `cascadeDelete: true` deletes PVCs; otherwise clean up with `kubectl delete pvc -n <ns> -l aerospike.io/cr-name=<name>`.

## 8. Template Resync (ops ref §5)

`kubectl annotate asc <name> -n <ns> acko.io/resync-template=true` (auto-removed). Status: `.status.templateSnapshot.synced`; drift events: `reason=TemplateDrifted`.

## 9. Clone Cluster (ops ref §11b)

Export the CR, strip `status`/identity metadata/`operations`/`paused`, rename, re-apply — exact `jq` recipe in ops ref §11b.

## 10. Clear Stuck Operations (ops ref §3)

Patch `spec.operations` to `null` (§4 command). Via cluster-manager API: `DELETE /api/k8s/clusters/{namespace}/{name}/operations`.

## 11-13. Network / PDB / Readiness Gate

`aerospikeNetworkPolicy.accessType`, LoadBalancer seeds, NetworkPolicy: ops ref §8. `disablePDB`, `maxUnavailable`, `k8sNodeBlockList`: ops ref §9. `podSpec.readinessGateEnabled`: ops ref §7.

## 14. Troubleshooting

For symptom-driven diagnosis (`phase=Error`, stuck migrations, `CrashLoopBackOff`, `CircuitBreakerActive`, `ConfigDegraded`, `ReadinessGateBlocking`, webhook rejection, `dynamicConfigStatus=Failed`), use the **`acko-debugging`** skill. It cross-links this skill's `reference/troubleshooting.md` (symptom→command table) and `reference/validation-rules.md` (canonical webhook error/warning catalog).

## 15. Diagnostics / Metrics / Events / OTel

kubectl one-liners: [`./reference/diagnostic-commands.md`](./reference/diagnostic-commands.md) · operator Prometheus metrics + alerts: [`./reference/metrics.md`](./reference/metrics.md) · K8s events catalog: [`./reference/events.md`](./reference/events.md) · operator OTel export (helm enable/verify): ops ref §13, chart config rules in **acko-deploy**.

---

Full Day-2 command detail: [Operations Reference](./reference/operations.md) · [Events](./reference/events.md) · [Troubleshooting](./reference/troubleshooting.md) · [Validation Rules](./reference/validation-rules.md) · [Diagnostic Commands](./reference/diagnostic-commands.md) · [Metrics](./reference/metrics.md)
