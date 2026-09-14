# Client Config Reference

## Table of Contents
- [ClientConfig](#clientconfig)
- [Connection Patterns](#connection-patterns)
- [Performance Tuning](#performance-tuning)

---

## ClientConfig

Import from `aerospike_py.types`. Used by `aerospike.client(config)` and `AsyncClient(config)`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| hosts | list[tuple[str, int]] | **required** | Seed host addresses |
| cluster_name | str \| None | None | Expected cluster name |
| auth_mode | int | AUTH_INTERNAL (0) | Authentication mode |
| user | str | None | Username for authentication |
| password | str | None | Password for authentication |
| timeout | int | 30000 | Connection timeout (ms) |
| idle_timeout | int | 30000 | Idle connection timeout (ms) |
| max_conns_per_node | int | 256 | Max connections per node |
| min_conns_per_node | int | 0 | Min connections per node (pre-warm) |
| conn_pools_per_node | int | 1 | Connection pools per node |
| tend_interval | int | 1000 | Cluster tend interval (ms) |
| use_services_alternate | bool | false | Use alternate service addresses |
| max_concurrent_operations | int | 0 (disabled) | Max in-flight operations (backpressure via Tokio Semaphore). Raises `BackpressureError` when exceeded. |
| operation_queue_timeout_ms | int | 0 (no timeout) | Timeout (ms) for waiting on an operation permit when backpressure is active |

### Basic Example

```python
import aerospike_py as aerospike
from aerospike_py.types import ClientConfig

config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "cluster_name": "docker",
}
client = aerospike.client(config).connect()
```

### Multi-Node Cluster

The client discovers all nodes from any reachable seed:

```python
config: ClientConfig = {
    "hosts": [
        ("node1.example.com", 3000),
        ("node2.example.com", 3000),
        ("node3.example.com", 3000),
    ],
}
```

### Authentication

Credentials go to `.connect(user, password)`, not the config dict; `auth_mode` selects the scheme:

```python
client = aerospike.client({"hosts": [...], "auth_mode": aerospike.AUTH_EXTERNAL}).connect("ldap_user", "ldap_pass")
```

`auth_mode` accepts only `AUTH_INTERNAL` (0), `AUTH_EXTERNAL` (1), or `AUTH_PKI` (2) — an unknown value is rejected client-side (no silent fallback to internal auth).

---

## Connection Patterns

`.connect()` returns the client (chainable). Both clients are context managers (`with` / `async with` → auto-close). Note the sync builder pattern `aerospike.client(config).connect()` vs the async `AsyncClient(config)` then `await client.connect()`.

```python
with aerospike.client(config).connect() as client: ...           # sync
async with aerospike.AsyncClient(config) as client:              # async
    await client.connect()
    record = await client.get(key)
```

---

## Performance Tuning

### Connection Pool Sizing

```python
config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "max_conns_per_node": 300,
    "min_conns_per_node": 10,
    "conn_pools_per_node": 1,
    "idle_timeout": 55000,
}
```

- **max_conns_per_node**: Match to expected concurrent requests per node.
- **min_conns_per_node**: Set > 0 to avoid cold-start latency spikes.
- **conn_pools_per_node**: Machines with 8 or fewer CPU cores need only 1. On machines with more cores, increasing this value reduces lock contention on pooled connections.
- **idle_timeout**: Keep below server `proto-fd-idle-ms` (default 60s).

### Timeout Configuration

| Setting | Recommendation |
|---------|---------------|
| `socket_timeout` | 1-5s. Catches hung connections. |
| `total_timeout` | Set based on SLA. Includes retries. |
| `max_retries` | 2-3 for reads. For writes see the note below — do **not** assume `0` means "no retries". |

#### `max_retries` is an attempt budget, and `0` is version-dependent

aerospike-py delegates the retry loop to `aerospike-core` (pinned in `rust/Cargo.toml`), and the two releases in circulation read the field differently:

| aerospike-core | retry cap in `src/commands/single_command.rs` | `max_retries: 0` | `max_retries: N > 0` |
|---|---|---|---|
| 2.0.0 (pinned today) | `if policy.max_retries() > 0 && iterations > policy.max_retries()` (:112) | cap disabled — every network error is re-sent until `total_timeout` expires | at most N attempts |
| 2.2.0 | `let effective_attempt = policy.max_retries() + 1;` … `if iterations > effective_attempt` (:106, :112) | exactly one attempt | at most N+1 attempts |

True on both: only network errors are retried, writes and `operate()` report `can_retry() == true`, and every retry is bounded by `total_timeout` — so `max_retries: 0` together with `total_timeout: 0` ("no limit") is an unbounded retry loop on 2.0.0. Never combine those two.

aerospike-py's `WritePolicy` default is `max_retries: 0` (`rust/src/policy/write_policy.rs`). On core 2.0.0 that is **not** "no retries": a connection reset arriving after the server committed the write causes a re-send, which double-counts an `increment()` and duplicates an `append()`. For a non-idempotent write — `increment()`, `append()`, `prepend()`, `operate()` with an increment op, `apply()` — set the value explicitly instead of inheriting the default: `policy={"max_retries": 1}` on core 2.0.0, `policy={"max_retries": 0}` on 2.2.0. Both give a single attempt on their respective core; a bounded `total_timeout` is required either way.

### Batch Size Recommendations

- Use `batch_read()` instead of sequential `get()` calls -- single round-trip vs N round-trips.
- Use `select()` or `batch_read(keys, bins=[...])` to read only needed bins, reducing network I/O.
- For numeric workloads, use `batch_read(keys).to_numpy(dtype)` for NumPy structured-array output (the `_dtype=` kwarg was removed).

### Expression Filters vs Secondary Indexes

Push filtering to the server to reduce network transfer:

```python
from aerospike_py import exp

# Server-side filtering (preferred -- less network transfer)
expr = exp.eq(exp.bool_bin("active"), exp.bool_val(True))
results = client.query("test", "demo").results(
    policy={"filter_expression": expr}
)
```

The policy key for expression filters is always `"filter_expression"`.

### Backpressure (Operation Concurrency Limiting)

Limit in-flight operations to prevent connection pool exhaustion under high load:

```python
config: ClientConfig = {
    "hosts": [("127.0.0.1", 3000)],
    "max_concurrent_operations": 64,       # Max 64 concurrent operations
    "operation_queue_timeout_ms": 5000,    # Wait up to 5s for a permit
}
```

When the limit is reached, new operations raise `BackpressureError` (or wait up to `operation_queue_timeout_ms`). Recommended for FastAPI / high-concurrency services.

### Tokio Runtime Workers

aerospike-py uses an internal Tokio async runtime with 2 worker threads by default. This is sufficient for most I/O-bound database operations.

```bash
# Override if you need more parallelism for heavy batch operations
export AEROSPIKE_RUNTIME_WORKERS=4
```

| Workers | Use Case |
|---------|----------|
| 2 (default) | Most applications, ML serving, web servers |
| 4 | Heavy batch operations, high-throughput pipelines |
| 8+ | Rarely needed; profile first |
