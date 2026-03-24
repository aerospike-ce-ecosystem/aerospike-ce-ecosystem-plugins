# Kubernetes Events Reference

Complete list of all 37 Kubernetes events emitted by the ACKO operator.

---

## Rolling Restart Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `RollingRestartStarted` | Normal | Rolling restart batch begins |
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

## Circuit Breaker Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `CircuitBreakerActive` | Warning | 10+ consecutive reconciliation failures; exponential backoff applied |
| `CircuitBreakerReset` | Normal | Successful reconciliation; circuit breaker reset |

---

## Other Events

| Event Reason | Type | When Emitted |
|---|---|---|
| `ValidationWarning` | Warning | Non-blocking validation warning |
| `ReconcileError` | Warning | Reconciliation error occurred |
| `Operation` | Normal | On-demand operation (WarmRestart/PodRestart) processing |
