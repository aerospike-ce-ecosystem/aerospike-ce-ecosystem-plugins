# Operator Metrics Catalog

Prometheus metrics emitted by the ACKO controller process (not the Aerospike server pods themselves — those are exposed via the optional exporter sidecar configured in `monitoring`).

The operator exposes metrics on the standard `controller-runtime` `/metrics` endpoint (default `:8080/metrics` in the `aerospike-operator` namespace).

> Catalog verified against `aerospike-ce-kubernetes-operator/internal/metrics/metrics.go`. Every metric below is registered with the listed labels.

---

## Cluster state

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_cluster_phase` | gauge | `cluster`, `namespace` | Numeric encoding of `status.phase` (0=Unknown, 1=InProgress, 2=Completed, 3=Error) |
| `acko_cluster_ready_pods` | gauge | `cluster`, `namespace` | Number of pods currently Ready in the cluster |
| `acko_cluster_as_size` | gauge | `cluster`, `namespace` | Cluster size reported by `asinfo` (may differ from K8s pod count during transitions) |
| `acko_cluster_migrating_partitions` | gauge | `cluster`, `namespace` | Total partitions remaining to be migrated across all nodes |

---

## Reconciliation health

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_reconcile_duration_seconds` | histogram | `cluster`, `namespace` | Per-reconcile wall time |
| `acko_last_reconcile_timestamp_seconds` | gauge | `cluster`, `namespace` | Unix timestamp of the last *successful* reconciliation (use age = `time() - acko_last_reconcile_timestamp_seconds`) |
| `acko_reconcile_errors_total` | counter | `cluster`, `namespace`, `reason` | Reconciliation errors by reason (covers both transient and permanent) |
| `acko_circuit_breaker_active` | gauge | `cluster`, `namespace` | `1` while the reconcile breaker is tripped, `0` otherwise. Stays `1` indefinitely on `PermanentError` (no auto-retry). |

> There is no `acko_reconcile_total{result="success"}` counter; success is observed via `acko_last_reconcile_timestamp_seconds` advancing.
> There is no `acko_failed_reconcile_count` Prometheus metric; the field exists only on `status.failedReconcileCount` (CR status).

### Useful PromQL

```promql
# Clusters with the breaker tripped right now
sum by (cluster, namespace) (acko_circuit_breaker_active == 1)

# Reconcile-error rate by reason (catches both transient and permanent)
sum by (cluster, reason) (rate(acko_reconcile_errors_total[15m]))

# How stale is the last successful reconcile? (alert when > 10m)
time() - max by (cluster, namespace) (acko_last_reconcile_timestamp_seconds)

# P95 reconcile latency
histogram_quantile(0.95, sum by (le, cluster) (rate(acko_reconcile_duration_seconds_bucket[5m])))
```

---

## Pause / Resume

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_cluster_paused_timestamp_seconds` | gauge | `cluster`, `namespace` | Unix timestamp of pause start; `0` when not paused. Derived from `ReconciliationPaused` condition's `lastTransitionTime`. |
| `acko_cluster_paused_duration_seconds` | histogram | `cluster`, `namespace` | Pause-cycle duration, observed when the cluster is resumed (i.e. on the `Paused → InProgress` transition). |

### Useful PromQL

```promql
# Currently paused clusters and how long they've been paused
(time() - acko_cluster_paused_timestamp_seconds) and (acko_cluster_paused_timestamp_seconds > 0)

# P95 pause duration over the last day
histogram_quantile(0.95, sum by (le, cluster) (rate(acko_cluster_paused_duration_seconds_bucket[1d])))
```

---

## Operations & ACL

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_warm_restarts_total` | counter | `cluster`, `namespace` | Warm restarts (SIGUSR1) performed via `spec.operations[]` or password rotation |
| `acko_cold_restarts_total` | counter | `cluster`, `namespace` | Cold restarts (pod delete + recreate) performed |
| `acko_dynamic_config_updates_total` | counter | `cluster`, `namespace` | Successful dynamic config updates via `set-config` (does NOT count failures or rollbacks) |
| `acko_acl_sync_total` | counter | `cluster`, `namespace` | ACL synchronization operations performed |
| `acko_scaledown_deferrals_total` | counter | `cluster`, `namespace` | Scale-down operations deferred because data migration was in progress |

> The current operator does not expose per-result counters for the 2PC dynamic config rollout (e.g., no `result=rolled_back` label on `acko_dynamic_config_updates_total`). To detect `ConfigDegraded`, monitor `acko_cluster_phase` for the corresponding numeric encoding (or, more reliably, query the CR status condition `DynamicConfigDegraded` directly via the `kube-state-metrics` `kube_customresource_*` series if exposed).

---

## Suggested alerts

```yaml
groups:
- name: acko-operator
  rules:
    - alert: ACKOCircuitBreakerActive
      expr: max by (cluster, namespace) (acko_circuit_breaker_active) == 1
      for: 5m
      annotations:
        summary: "ACKO circuit breaker tripped for {{ $labels.cluster }}"
        runbook: "Check status.conditions[ReconcileHealthy]; if reason=PermanentError, fix root cause and toggle paused to clear stale state."

    - alert: ACKOReconcileStale
      expr: (time() - max by (cluster, namespace) (acko_last_reconcile_timestamp_seconds)) > 600
      for: 5m
      annotations:
        summary: "{{ $labels.cluster }} has not reconciled successfully in over 10 minutes"

    - alert: ACKOReconcileErrorRate
      expr: sum by (cluster, reason) (rate(acko_reconcile_errors_total[10m])) > 0.1
      for: 10m
      annotations:
        summary: "{{ $labels.cluster }} reconcile errors ({{ $labels.reason }}) at high rate"

    - alert: ACKOClusterPausedTooLong
      expr: (time() - acko_cluster_paused_timestamp_seconds > 86400) and (acko_cluster_paused_timestamp_seconds > 0)
      annotations:
        summary: "{{ $labels.cluster }} has been paused for over 24h"

    - alert: ACKOMigrationStuck
      expr: acko_cluster_migrating_partitions > 0
      for: 1h
      annotations:
        summary: "{{ $labels.cluster }} has been migrating partitions for over 1h"
```
