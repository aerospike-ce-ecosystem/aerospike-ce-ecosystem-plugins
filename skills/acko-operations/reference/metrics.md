# Operator Metrics Catalog

Prometheus metrics emitted by the ACKO controller process (not the Aerospike server pods themselves — those are exposed via the optional exporter sidecar configured in `monitoring`).

The operator exposes metrics on the standard `controller-runtime` `/metrics` endpoint (default `:8080/metrics` in the `aerospike-operator` namespace).

When `observability.otel.enabled` is set on the Helm chart, this same registry is **also** pushed to an OTLP collector (bridged from Prometheus) — `/metrics` scraping and OTLP push run side by side. See acko-operations §16.

> Catalog verified against `aerospike-ce-kubernetes-operator/internal/metrics/metrics.go`. Every metric below is registered with the listed labels. The cluster is identified by the label pair `namespace`, `name` (there is no `cluster` label).

---

## Cluster state

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_cluster_phase` | gauge | `namespace`, `name` | Numeric encoding of `status.phase` — see mapping below |
| `acko_cluster_ready_pods` | gauge | `namespace`, `name` | Number of pods currently Ready in the cluster |
| `acko_cluster_as_size` | gauge | `namespace`, `name` | Cluster size reported by `asinfo` (may differ from K8s pod count during transitions) |
| `acko_cluster_migrating_partitions` | gauge | `namespace`, `name` | Total partitions remaining to be migrated across all nodes |

`acko_cluster_phase` encoding (`metrics.PhaseToFloat`): 1=InProgress, 2=Completed, 3=Error, 4=ScalingUp, 5=ScalingDown, 6=WaitingForMigration, 7=RollingRestart, 8=ACLSync, 9=Paused, 10=Deleting, 11=BackoffActive, **12=ConfigDegraded**, 0=anything else. `ConfigDegraded` is reported on the gauge as soon as the phase is set (alert: `acko_cluster_phase == 12`).

---

## Reconciliation health

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_reconcile_duration_seconds` | histogram | `namespace`, `name` | Per-reconcile wall time |
| `acko_last_reconcile_timestamp_seconds` | gauge | `namespace`, `name` | Unix timestamp of the last *successful* reconciliation (use age = `time() - acko_last_reconcile_timestamp_seconds`) |
| `acko_reconcile_errors_total` | counter | `namespace`, `name`, `reason` | Reconciliation errors by reason (covers both transient and permanent) |
| `acko_circuit_breaker_active` | gauge | `namespace`, `name` | `1` while the reconcile breaker is tripped, `0` otherwise. Stays `1` indefinitely on `PermanentError` (no auto-retry); transient backoff is exponential, capped at 5 min. |

> There is no `acko_reconcile_total{result="success"}` counter; success is observed via `acko_last_reconcile_timestamp_seconds` advancing.
> There is no `acko_failed_reconcile_count` Prometheus metric; the field exists only on `status.failedReconcileCount` (CR status).

### Useful PromQL

```promql
# Clusters with the breaker tripped right now
sum by (namespace, name) (acko_circuit_breaker_active == 1)

# Reconcile-error rate by reason (catches both transient and permanent)
sum by (name, reason) (rate(acko_reconcile_errors_total[15m]))

# How stale is the last successful reconcile? (alert when > 10m)
time() - max by (namespace, name) (acko_last_reconcile_timestamp_seconds)

# P95 reconcile latency
histogram_quantile(0.95, sum by (le, name) (rate(acko_reconcile_duration_seconds_bucket[5m])))
```

---

## Pause / Resume

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_cluster_paused_timestamp_seconds` | gauge | `namespace`, `name` | Unix timestamp of pause start; `0` when not paused. Derived from `ReconciliationPaused` condition's `lastTransitionTime`. |
| `acko_cluster_paused_duration_seconds` | histogram | `namespace`, `name` | Pause-cycle duration, observed when the cluster is resumed (i.e. on the `Paused → InProgress` transition). |

### Useful PromQL

```promql
# Currently paused clusters and how long they've been paused
(time() - acko_cluster_paused_timestamp_seconds) and (acko_cluster_paused_timestamp_seconds > 0)

# P95 pause duration over the last day
histogram_quantile(0.95, sum by (le, name) (rate(acko_cluster_paused_duration_seconds_bucket[1d])))
```

---

## Operations & ACL

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_warm_restarts_total` | counter | `namespace`, `name` | Warm restarts (SIGUSR1) performed via `spec.operations[]` or password rotation |
| `acko_cold_restarts_total` | counter | `namespace`, `name` | Cold restarts (pod delete + recreate) performed |
| `acko_dynamic_config_updates_total` | counter | `namespace`, `name` | Successful dynamic config updates via `set-config` (does NOT count failures or rollbacks) |
| `acko_acl_sync_total` | counter | `namespace`, `name`, `result` | ACL synchronization attempts (`result` = `success` \| `error`) |
| `acko_scaledown_deferrals_total` | counter | `namespace`, `name` | Scale-down operations deferred because data migration was in progress |

> The current operator does not expose per-result counters for the 2PC dynamic config rollout (e.g., no `result=rolled_back` label on `acko_dynamic_config_updates_total`). To detect `ConfigDegraded`, alert on `acko_cluster_phase == 12` (reported as soon as the phase is set).

---

## Suggested alerts

```yaml
groups:
- name: acko-operator
  rules:
    - alert: ACKOCircuitBreakerActive
      expr: max by (namespace, name) (acko_circuit_breaker_active) == 1
      for: 5m
      annotations:
        summary: "ACKO circuit breaker tripped for {{ $labels.name }}"
        runbook: "Check status.conditions[ReconcileHealthy]; if reason=PermanentError, fix root cause and toggle paused to clear stale state."

    - alert: ACKOConfigDegraded
      expr: max by (namespace, name) (acko_cluster_phase) == 12
      for: 5m
      annotations:
        summary: "{{ $labels.name }} is ConfigDegraded — reconcile halted until manual intervention"

    - alert: ACKOReconcileStale
      expr: (time() - max by (namespace, name) (acko_last_reconcile_timestamp_seconds)) > 600
      for: 5m
      annotations:
        summary: "{{ $labels.name }} has not reconciled successfully in over 10 minutes"

    - alert: ACKOReconcileErrorRate
      expr: sum by (name, reason) (rate(acko_reconcile_errors_total[10m])) > 0.1
      for: 10m
      annotations:
        summary: "{{ $labels.name }} reconcile errors ({{ $labels.reason }}) at high rate"

    - alert: ACKOClusterPausedTooLong
      expr: (time() - acko_cluster_paused_timestamp_seconds > 86400) and (acko_cluster_paused_timestamp_seconds > 0)
      annotations:
        summary: "{{ $labels.name }} has been paused for over 24h"

    - alert: ACKOMigrationStuck
      expr: acko_cluster_migrating_partitions > 0
      for: 1h
      annotations:
        summary: "{{ $labels.name }} has been migrating partitions for over 1h"
```
