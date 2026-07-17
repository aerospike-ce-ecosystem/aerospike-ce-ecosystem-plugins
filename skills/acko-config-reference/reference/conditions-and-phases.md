# AerospikeCluster Phases & Conditions

This is background reference for `status.phase` and `status.conditions[]` on the `AerospikeCluster` CR. ACKO uses these to communicate reconciliation state. Operations procedures live in `acko-operations`.

---

## status.phase

Exact `AerospikePhase` enum (operator `aerospikecluster_types.go`). There is no `Pending` phase — the generic in-flight phase is `InProgress`.

| Phase | Meaning |
|-------|---------|
| `""` (empty) | CR just created, reconciler has not yet observed it |
| `InProgress` | Generic in-flight reconcile (creation, resume, config apply) |
| `Completed` | Spec fully realized; all pods Ready, generations matched, ACL synced, no in-flight ops |
| `Error` | Unrecoverable reconcile error (distinct from the circuit-breaker `BackoffActive`) |
| `ScalingUp` / `ScalingDown` | Pods being added / removed |
| `WaitingForMigration` | Scale-down deferred until data migration drains |
| `RollingRestart` | Rolling restart in progress (image/static-config change) |
| `ACLSync` | ACL roles/users syncing — **if stuck here, ACL sync is failing** (see below) |
| `Paused` | Reconciliation suspended via `spec.paused: true` |
| `Deleting` | Cluster deletion in progress |
| `ConfigDegraded` | 2PC dynamic config apply AND LIFO rollback both failed; pods hold inconsistent runtime config; reconcile halts until manual intervention |
| `BackoffActive` | Reconcile circuit breaker tripped; requeue with exponential backoff (capped at 5 min) |

### `Phase = ACLSync` (stuck) — ACL failure does NOT reach Completed

On an ACL sync failure the reconcile publishes `phase=ACLSync` (reason `"ACL synchronization failed; will retry: ..."`) and requeues every ~30s — it does **not** report `Completed`. A Secret change doesn't bump the CR generation, so the explicit requeue is the only prompt retry. Check the `ACLSynced` condition / `ACLSyncError` event / the password Secret.

### `Phase = BackoffActive` — circuit breaker

The reconcile-failure circuit breaker tripped (`failedReconcileCount` at max). Emits the `CircuitBreakerActive` event and sets `acko_circuit_breaker_active=1`. **Two flavors**, distinguished by the `ReconcileHealthy` condition:
- `ReconcileHealthy=True` — transient cause (pod not ready, image pull, capacity); auto-retries with backoff.
- `ReconcileHealthy=False, reason=PermanentError` — validation/configgen/missing-Secret error; no retry until you fix the spec or toggle `paused: true → null` (which clears stale `failedReconcileCount`/`lastReconcileError`).

### `Phase = ConfigDegraded` — 2PC rollback failed

A 2-phase-commit dynamic config update had its apply fail mid-flight AND the LIFO rollback also fail, so pods hold different runtime configs. The operator **halts reconciliation** for the cluster — it skips every reconcile with a `ConfigDegradedSkip` Warning event (requeue every ~60s) until a human intervenes, because re-running the reconcile could re-apply the broken change and amplify the divergence. To diagnose: read the `DynamicConfigDegraded=True` condition message and `status.pods[].dynamicConfigChanges` (per-path old/new/result). To recover: revert the offending value in `spec.aerospikeConfig` (roll back manually), then cold-restart the pods / reset the phase so reconciliation resumes.

---

## status.conditions[]

Each condition has `type`, `status` (`True`/`False`/`Unknown`), `reason`, `message`, `lastTransitionTime`. Full set (operator `aerospikecluster_types.go`):

| Type | `True` means |
|------|--------------|
| `Available` | at least one pod is Ready |
| `Ready` | all desired pods are running and Ready |
| `ConfigApplied` | every pod carries an accepted config hash (per-rack aware — see below) |
| `ACLSynced` | ACL roles/users synced (only set when ACL is configured; cleared when ACL removed) |
| `MigrationComplete` | no data migrations pending |
| `ReconciliationPaused` | `spec.paused: true` in effect |
| `ReconcileHealthy` | `False` = circuit broken (reasons `PermanentError`, `Recovered`) |
| `DynamicConfigDegraded` | pods hold inconsistent dynamic config (reasons `RollbackFailed`, `ApplyFailed`) |

### `ConfigApplied`

Each pod carries the **effective per-rack** config hash — (cluster config DeepMerged with `rack.AerospikeConfig`). The condition accepts a pod whose hash is in the valid per-rack hash set, so a rack that overrides config no longer pins `ConfigApplied=False` forever after convergence.

### `ReconcileHealthy = False / reason = PermanentError`

Circuit breaker active with an unrecoverable error (configgen rejected a value, missing Secret, escaped webhook failure). Phase is `BackoffActive`; `failedReconcileCount` pinned at max, no backoff to wait through. Recover by fixing the root cause then editing the spec, OR toggling `spec.paused: true → null` to clear stale state.

### `DynamicConfigDegraded = True`

Set together with `phase=ConfigDegraded`; read `status.pods[].dynamicConfigChanges` for per-pod detail.

### `ReconciliationPaused = True`

Set together with `phase=Paused`. Its `lastTransitionTime` is the canonical pause-start — `acko_cluster_paused_timestamp_seconds` / `acko_cluster_paused_duration_seconds` derive from it.

---

## status.pods[].dynamicConfigChanges (NEW)

Each `AerospikePodStatus.dynamicConfigChanges[]` entry tracks one config path mutated in the last dynamic config attempt:

| Field | Type | Description |
|-------|------|-------------|
| `path` | string | Dotted config path, e.g. `service.proto-fd-max` |
| `oldValue` | string | Previous value (TOML-rendered) |
| `newValue` | string | Attempted new value |
| `result` | enum | `Applied`, `Failed`, `Pending`, `RolledBack`, `RollbackFailed` |

Use this to debug which specific change failed in a 2PC rollout:

```bash
kubectl get asc <name> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' | jq
```

---

## Quick decision tree

```
status.phase == Completed
  -> healthy steady state

status.phase == InProgress / ScalingUp / ScalingDown / RollingRestart (transient)
  -> wait one reconcile cycle; check events for hints

status.phase == ACLSync (stuck)
  -> ACL sync failing -> check ACLSynced condition / ACLSyncError event / Secret

status.phase == ConfigDegraded
  -> 2PC dynamic config rollback failed
  -> read DynamicConfigDegraded condition + status.pods[].dynamicConfigChanges
  -> reconcile is HALTED (ConfigDegradedSkip events every ~60s) until you
     revert the bad config and cold-restart / reset the phase

status.phase == BackoffActive
  -> circuit breaker tripped
  -> if ReconcileHealthy==False/PermanentError: fix root cause; toggle paused or edit spec
  -> else transient: auto-retries with backoff

status.conditions[ReconciliationPaused].status == True
  -> spec.paused == true; nothing happens until you resume
```
