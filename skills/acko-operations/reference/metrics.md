# Operator Metrics Catalog

Prometheus metrics emitted by the ACKO controller process (not the Aerospike server pods themselves — those are exposed via the optional exporter sidecar configured in `monitoring`).

The operator exposes metrics on the standard `controller-runtime` `/metrics` endpoint (default `:8080/metrics` inside the `aerospike-operator` namespace).

---

## Reconciliation health

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_reconcile_total` | counter | `cluster`, `namespace`, `result` | Reconcile attempts. `result` ∈ {`success`, `error`, `permanent_error`} |
| `acko_reconcile_duration_seconds` | histogram | `cluster`, `namespace` | Per-reconcile wall time |
| `acko_failed_reconcile_count` | gauge | `cluster`, `namespace` | Mirrors `status.failedReconcileCount` |
| `acko_circuit_breaker_active` | gauge | `cluster`, `namespace` | `1` while breaker tripped, `0` otherwise. Stays `1` indefinitely on `PermanentError`. |

### Useful PromQL

```promql
# Clusters with the breaker tripped right now
sum by (cluster, namespace) (acko_circuit_breaker_active == 1)

# Permanent-error rate (tells you what a human will need to look at)
rate(acko_reconcile_total{result="permanent_error"}[15m])

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

## Dynamic config / 2PC

| Metric | Type | Labels | Meaning |
|--------|------|--------|---------|
| `acko_dynamic_config_apply_total` | counter | `cluster`, `namespace`, `result` | One increment per pod applied. `result` ∈ {`applied`, `failed`, `rolled_back`, `rollback_failed`} |
| `acko_dynamic_config_validation_failed_total` | counter | `cluster`, `namespace` | Phase 1 abort count (any pod rejected the change) |

### Useful PromQL

```promql
# Per-cluster ConfigDegraded entries (rollback_failed implies degraded)
sum by (cluster) (rate(acko_dynamic_config_apply_total{result="rollback_failed"}[1h]))
```

---

## Suggested alerts

```yaml
groups:
- name: acko-operator
  rules:
    - alert: ACKOPermanentReconcileError
      expr: max by (cluster, namespace) (rate(acko_reconcile_total{result="permanent_error"}[15m])) > 0
      for: 5m
      annotations:
        summary: "ACKO has stopped retrying {{ $labels.cluster }} due to a permanent error"
        runbook: "Check status.conditions[ReconcileHealthy] and status.lastReconcileError; toggle paused after fixing root cause."

    - alert: ACKOConfigDegraded
      expr: max by (cluster, namespace) (rate(acko_dynamic_config_apply_total{result="rollback_failed"}[1h])) > 0
      annotations:
        summary: "Dynamic config rollback failed on {{ $labels.cluster }}"
        runbook: "Operator will cold-restart on next reconcile. Inspect status.pods[*].dynamicConfigChanges."

    - alert: ACKOClusterPausedTooLong
      expr: (time() - acko_cluster_paused_timestamp_seconds > 86400) and (acko_cluster_paused_timestamp_seconds > 0)
      annotations:
        summary: "{{ $labels.cluster }} has been paused for over 24h"
```
