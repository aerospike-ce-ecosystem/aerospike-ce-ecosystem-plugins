# Observability Reference

Prometheus metrics + OpenTelemetry tracing for `aerospike-py`. Both are built into the Rust core and exposed through plain Python helpers — no extra service mesh required to get end-to-end visibility.

## Table of Contents
- [Quick Start](#quick-start)
- [Prometheus Metrics](#prometheus-metrics)
- [OpenTelemetry Tracing](#opentelemetry-tracing)
- [FastAPI Integration](#fastapi-integration)
- [Environment Variables](#environment-variables)
- [Logging](#logging)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```python
import aerospike_py

aerospike_py.start_metrics_server(port=9464)   # Prometheus /metrics endpoint
aerospike_py.init_tracing()                    # OTLP gRPC exporter via OTEL_* env

# ... your client work happens with metrics + traces auto-collected ...

aerospike_py.shutdown_tracing()                # flush spans before exit
aerospike_py.stop_metrics_server()
```

`start_metrics_server` only takes `port` (binds on all interfaces — there is no `addr=` argument). Default is `9464` (the OpenMetrics conventional port). Both functions are thread-safe and idempotent.

---

## Prometheus Metrics

Operation-level metrics collected in Rust, exposed in Prometheus text format. Metric names follow OpenTelemetry DB Client Semantic Conventions.

### API

| Function | Description |
|----------|-------------|
| `start_metrics_server(port=9464)` | Background HTTP server at `http://<host>:<port>/metrics` |
| `stop_metrics_server()` | Shut down the metrics server |
| `get_metrics() -> str` | Snapshot the current metrics as Prometheus text |
| `set_metrics_enabled(enabled: bool)` | Toggle collection (~1 ns when disabled, useful for benchmarks) |
| `is_metrics_enabled() -> bool` | Current state |

### Metric: `db_client_operation_duration_seconds`

Histogram. Labels: `db_system_name` (always `aerospike`), `db_namespace`, `db_collection_name`, `db_operation_name`, `error_type` (empty on success, exception name on failure). Buckets: `0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0` seconds.

Instrumented operations: `put`, `get`, `select`, `exists`, `remove`, `touch`, `append`, `prepend`, `increment`, `operate`, `batch_read`, `batch_operate`, `batch_remove`, `batch_write`, `query`. (`exists()` treats `KeyNotFoundError` as success.)

### Example output

```
# HELP db_client_operation_duration_seconds Aerospike client operation latency
# TYPE db_client_operation_duration_seconds histogram
db_client_operation_duration_seconds_bucket{db_namespace="test",db_collection_name="users",db_operation_name="put",error_type="",le="0.001"} 142
db_client_operation_duration_seconds_count{...} 192
db_client_operation_duration_seconds_sum{...} 0.214
```

### PromQL recipes

```promql
# P99 latency by operation
histogram_quantile(0.99, sum by (db_operation_name, le) (rate(db_client_operation_duration_seconds_bucket[5m])))

# Error rate by error_type
sum by (error_type) (rate(db_client_operation_duration_seconds_count{error_type!=""}[5m]))

# Ops/sec by namespace
sum by (db_namespace) (rate(db_client_operation_duration_seconds_count[1m]))
```

---

## OpenTelemetry Tracing

```python
aerospike_py.init_tracing()      # reads OTEL_* env, sets up OTLP gRPC exporter
aerospike_py.shutdown_tracing()  # flush pending spans; call before process exit
```

Both calls are no-ops if `OTEL_SDK_DISABLED=true` is set. With `pip install aerospike-py[otel]`, W3C TraceContext is propagated from any active Python span — your aerospike spans become children of the FastAPI/Starlette/httpx parent automatically.

### Span attributes

| Attribute | Example |
|-----------|---------|
| `db.system.name` | `aerospike` |
| `db.namespace` | `test` |
| `db.collection.name` | `users` |
| `db.operation.name` | `PUT`, `GET`, `BATCH_READ` |
| `error.type` | (on failure) `RecordNotFound` |

Span name is `{OPERATION} {namespace}.{set}` (e.g. `PUT test.users`).

---

## FastAPI Integration

Wire metrics + tracing into your app's lifespan so they boot and shut down with the server.

```python
from contextlib import asynccontextmanager

import aerospike_py
from aerospike_py import AsyncClient
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot observability before opening the client so connect() spans are captured.
    aerospike_py.start_metrics_server(port=9464)
    aerospike_py.init_tracing()  # OTLP exporter via OTEL_EXPORTER_OTLP_ENDPOINT

    client = AsyncClient({"hosts": [("aerospike", 3000)], "max_concurrent_operations": 64})
    await client.connect()
    app.state.aerospike = client

    yield

    await client.close()
    aerospike_py.shutdown_tracing()
    aerospike_py.stop_metrics_server()


app = FastAPI(lifespan=lifespan)
```

The metrics server runs on its own daemon thread (separate port from your FastAPI server) — Prometheus scrapes `http://<pod>:9464/metrics`. If you must serve `/metrics` from the FastAPI port instead, expose your own route returning `aerospike_py.get_metrics()` and skip `start_metrics_server()`:

```python
from fastapi.responses import PlainTextResponse

@app.get("/metrics")
def metrics() -> PlainTextResponse:
    return PlainTextResponse(aerospike_py.get_metrics(), media_type="text/plain; version=0.0.4")
```

---

## Environment Variables

`aerospike-py` honors the standard OpenTelemetry environment variables. No client-side knobs — configure via env to keep deployments declarative.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OTEL_SERVICE_NAME` | `aerospike-py` | Service name on every span |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector endpoint |
| `OTEL_EXPORTER_OTLP_HEADERS` | (unset) | Comma-separated `key=value` headers (auth tokens etc.) |
| `OTEL_TRACES_EXPORTER` | `otlp` | Set to `none` to keep span creation but disable export |
| `OTEL_SDK_DISABLED` | `false` | Disable tracing entirely (init_tracing becomes a no-op) |
| `AEROSPIKE_PY_INTERNAL_METRICS` | `0` | Set `1` to enable internal stage profiling on startup |

Compose / Kubernetes example:

```yaml
env:
  - { name: OTEL_SERVICE_NAME,           value: "checkout-api" }
  - { name: OTEL_EXPORTER_OTLP_ENDPOINT, value: "http://otel-collector:4317" }
  - { name: OTEL_EXPORTER_OTLP_HEADERS,  value: "authorization=Bearer ${OTLP_TOKEN}" }
```

---

## Logging

Rust-to-Python logging bridge (forwarded to the standard `logging` module).

```python
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)   # OFF=-1, ERR=0, WARN=1, INFO=2, DBG=3, TRACE=4
aerospike_py.dropped_log_count()                            # back-pressure counter for slow sinks
```

Logger names: `aerospike_core::cluster`, `aerospike_core::batch`, `aerospike_core::command`, `aerospike_py`.

---

## Troubleshooting

- **`/metrics` returns empty histograms** — no operations have run yet, or `set_metrics_enabled(False)` is in effect. Issue a single `put`/`get` and re-scrape.
- **No spans in collector** — verify `OTEL_EXPORTER_OTLP_ENDPOINT` is reachable (gRPC, default port `4317`). `init_tracing()` logs a warning and silently disables on connection failure; check the `aerospike_py` logger at `INFO`.
- **Spans are root, not children of my Python span** — install the OTel extra: `pip install aerospike-py[otel]`. Without it the Rust core cannot read W3C TraceContext from the active Python span.
- **`start_metrics_server` raises `OSError: address already in use`** — another process holds the port; pick a free one or call `stop_metrics_server()` first. Same-port restarts within the same process are handled automatically.
- **Pending spans lost on shutdown** — always call `aerospike_py.shutdown_tracing()` from your lifespan/atexit handler. The OTLP exporter buffers spans and flushes on shutdown.
