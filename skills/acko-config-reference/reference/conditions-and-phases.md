# AerospikeCluster Phases & Conditions

This is background reference for `status.phase` and `status.conditions[]` on the `AerospikeCluster` CR. ACKO uses these to communicate reconciliation state. Operations procedures live in `acko-operations`.

---

## status.phase

| Phase | Meaning | Triggers |
|-------|---------|----------|
| `""` (empty) | CR just created, reconciler has not yet observed it | Initial admission |
| `Pending` | Reconciler observed CR, work is in flight | First reconcile loop |
| `Completed` | Spec is fully realized; cluster is healthy and stable | All pods Ready, generations matched, no in-flight ops |
| `Error` | A reconcile attempt failed and is being retried | Transient errors (pod not ready, network), exponential backoff |
| `Paused` | Reconciliation suspended via `spec.paused: true` | User toggled `paused: true` |
| `ConfigDegraded` | Dynamic config rollback failed; cluster is in inconsistent config state across pods | 2PC apply failed AND LIFO rollback also failed |

### `Phase = Completed`

The expected steady state. All pods Ready, observed generation matches spec generation, no operations in progress.

### `Phase = Error`

Reconciler will retry with exponential backoff. **Note:** for permanent errors (validation, missing secrets), the circuit breaker activates immediately and `status.conditions` will include `ReconcileHealthy=False` with `reason=PermanentError` -- in that case the backoff is bypassed and no further retries happen until you fix the spec or toggle `paused`.

### `Phase = Paused`

Set when `spec.paused: true`. The reconciler stops touching the cluster. Resume by setting `spec.paused: null` (or `false`); on resume, stale `status.failedReconcileCount` and `status.lastReconcileError` are cleared.

### `Phase = ConfigDegraded` (NEW, April 2026)

Dynamic config update used a 2-phase commit (validate-all-then-apply-all). Apply failed mid-flight, and the LIFO rollback also failed -- so different pods now have different runtime configs. The operator will attempt a cold restart on the next reconcile to get back to the spec'd config.

Recovery is automatic on the next reconcile, but you should:
1. Inspect `status.conditions` for `DynamicConfigDegraded=True` and read its `message`.
2. Inspect `status.pods[].dynamicConfigChanges` to see which path/oldValue/newValue per pod.
3. If the cold restart loop continues, fix the underlying spec problem (e.g., a config value that's invalid on some hardware shape).

---

## status.conditions[]

ACKO emits standard K8s-style conditions. Each has `type`, `status` (`True`/`False`/`Unknown`), `reason`, `message`, `lastTransitionTime`.

| Type | Status meaning | Reason examples |
|------|----------------|-----------------|
| `ReconcileHealthy` | `True` = recent reconciles succeeded; `False` = circuit broken | `PermanentError`, `Recovered` |
| `DynamicConfigDegraded` | `True` = pods have inconsistent dynamic config | `RollbackFailed`, `ApplyFailed` |
| `ReconciliationPaused` | `True` = `spec.paused: true` is in effect | `UserRequested` |

### `ReconcileHealthy = False / reason = PermanentError`

Circuit breaker is active. The operator detected an unrecoverable error (e.g., configgen rejected a value, a required Secret is missing, a webhook validation failure that somehow escaped admission) and stopped retrying. `status.failedReconcileCount` is pinned at the max value -- there is no incremental backoff to wait through.

To recover:
- Fix the root cause (correct the spec, create the missing Secret, etc.).
- Either edit the spec to retrigger a reconcile, OR toggle `spec.paused: true` then `spec.paused: null` to clear the stale `failedReconcileCount` and `lastReconcileError`.

### `DynamicConfigDegraded = True`

Set together with `phase=ConfigDegraded`. See above. Read `status.pods[].dynamicConfigChanges` for per-pod detail.

### `ReconciliationPaused = True`

Set together with `phase=Paused`. The condition's `lastTransitionTime` is the canonical "when did pause start" — the `acko_cluster_paused_timestamp_seconds` and `acko_cluster_paused_duration_seconds` metrics are derived from it.

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

status.phase == Pending or Error (transient)
  -> wait one reconcile cycle; check events for hints

status.phase == ConfigDegraded
  -> 2PC dynamic config rollback failed
  -> read DynamicConfigDegraded condition + status.pods[].dynamicConfigChanges
  -> operator will cold-restart on next reconcile

status.conditions[ReconcileHealthy].status == False, reason == PermanentError
  -> circuit broken on a permanent error
  -> fix root cause; toggle paused or edit spec to retrigger

status.conditions[ReconciliationPaused].status == True
  -> spec.paused == true; nothing happens until you resume
```
