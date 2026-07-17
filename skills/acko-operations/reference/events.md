# Kubernetes Events Reference

Catalog of Kubernetes events emitted by the ACKO operator. Count grows over releases — see sections below.

---

## Rolling Restart Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `RollingRestartStarted` | Normal | Rolling restart batch begins |
| `RollingRestartDeferred` | Warning | Restart batch deferred because data migration is in flight (mirrors `ScaleDownDeferred`) |
| `RollingRestartCompleted` | Normal | All target pods have been restarted |
| `RestartFailed` | Warning | A pod restart failed |
| `PodWarmRestarted` | Normal | SIGUSR1 warm restart completed for a pod |
| `PodColdRestarted` | Normal | Pod deleted and recreated (cold restart completed) |

---

## Quiesce Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `NodeQuiesceStarted` | Normal | Node quiesce operation started |
| `NodeQuiesced` | Normal | Node quiesce operation completed |
| `NodeQuiesceFailed` | Warning | Node quiesce operation failed |

---

## Configuration Management Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `ConfigMapCreated` | Normal | New ConfigMap created for a rack |
| `ConfigMapUpdated` | Normal | ConfigMap contents updated |
| `DynamicConfigApplied` | Normal | Dynamic config change (set-config) succeeded |
| `DynamicConfigStatusFailed` | Warning | Dynamic config change failed |

### Dynamic Config 2-Phase Commit (April 2026)

| Event Reason | Type | When Emitted |
|---|---|---|
| `DynamicConfigValidationFailed` | Warning | Phase 1 (validate-all) rejected the change on at least one pod; whole update aborted before any pod is mutated |
| `DynamicConfigRollbackTriggered` | Warning | Phase 2 apply failed on a pod; LIFO rollback started across already-updated pods |
| `DynamicConfigRollbackFailed` | Warning | Rollback itself failed; cluster transitioning to `phase=ConfigDegraded` |
| `DynamicConfigDegraded` | Warning | `ConditionDynamicConfigDegraded=True` set; reconciliation halts until manual intervention |
| `ConfigDegradedSkip` | Warning | Reconcile skipped because the cluster is in `phase=ConfigDegraded` (message: `"Reconcile skipped due to ConfigDegraded phase"`; repeats every ~60s until resolved) |

> There is **no recovery event** when `ConfigDegraded` is resolved — the operator emits nothing on convergence. Observe recovery via `status.phase` returning to `Completed` and the `DynamicConfigDegraded` condition being removed.

---

## StatefulSet / Rack Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `StatefulSetCreated` | Normal | New StatefulSet created for a rack |
| `StatefulSetUpdated` | Normal | StatefulSet spec updated |
| `RackScaled` | Normal | Rack pod count changed |
| `ScaleDownDeferred` | Warning | Scale-down deferred due to data migration in progress |
| `PVCCleanedUp` | Normal | PVC cleanup completed for deleted pod |
| `PVCCleanupFailed` | Warning | PVC cleanup failed |

---

## ACL Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `ACLSyncStarted` | Normal | ACL synchronization started |
| `ACLSyncCompleted` | Normal | ACL synchronization completed successfully |
| `ACLSyncError` | Warning | ACL synchronization failed |

---

## PDB / Service Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `PDBCreated` | Normal | PodDisruptionBudget created |
| `PDBUpdated` | Normal | PodDisruptionBudget updated |
| `ServiceCreated` | Normal | Kubernetes Service created |
| `ServiceUpdated` | Normal | Kubernetes Service updated |

---

## Cluster Lifecycle Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `ClusterDeletionStarted` | Normal | Cluster deletion processing started |
| `FinalizerRemoved` | Normal | Finalizer removed just before CR deletion |

---

## Template Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `TemplateApplied` | Normal | Template snapshot applied successfully |
| `TemplateResolutionError` | Warning | Template resolution/parsing failed |
| `TemplateDrifted` | Warning | Referenced template changed since last snapshot |

---

## Readiness Gate Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `ReadinessGateSatisfied` | Normal | Readiness gate condition met |
| `ReadinessGateBlocking` | Warning | Readiness gate not satisfied; blocking rolling restart |

---

## Circuit Breaker / Permanent Error Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `CircuitBreakerActive` | Warning | Reconcile failure threshold reached (transient errors → exponential backoff) |
| `CircuitBreakerReset` | Normal | Successful reconciliation; circuit breaker reset |
| `PermanentError` | Warning | Validation/configgen/secret error detected; `ConditionReconcileHealthy=False` (`Reason=PermanentError`); `failedReconcileCount` pinned at max with NO retry |

## Pause / Resume Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `ClusterPaused` | Normal | `spec.paused=true` observed; reconciliation suspended; `ConditionReconciliationPaused=True` |
| `ClusterResumed` | Normal | `spec.paused` cleared; `failedReconcileCount`/`lastReconcileError` cleared; `ConditionReconciliationPaused=False` |

---

## Other Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `ValidationWarning` | Warning | Non-blocking validation warning |
| `ReconcileError` | Warning | Reconciliation error occurred |
| `Operation` | Normal | On-demand operation (WarmRestart/PodRestart) processing |
