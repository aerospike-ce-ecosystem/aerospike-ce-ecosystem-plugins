---
name: aerospike-py-api
description: "MUST USE when writing any Python code with aerospike-py or aerospike_py. This is a Rust/PyO3 library with UNCONVENTIONAL patterns that differ from typical Python clients — exceptions live on the module (aerospike_py.RecordNotFound, NOT aerospike_py.exception.RecordNotFound), return types are NamedTuples (record.bins, record.meta.gen, NOT tuple unpacking), batch_read returns dict[UserKey, AerospikeRecord] (NOT BatchRecords), and policies use module-level constants (aerospike_py.POLICY_EXISTS_CREATE_ONLY). Without this skill, code will use wrong import paths, wrong return type patterns, and miss critical features like expression filters (exp module), batch_write with in_doubt retry semantics, CDT list/map/bit/hll, ping() health check, backpressure, Prometheus metrics, OpenTelemetry tracing, NumPy integration, and admin APIs. Triggers on: aerospike-py, aerospike_py, AsyncClient, client.ping(), batch_write, Python + Aerospike, put/get/query/batch with Aerospike."
---

## Installation

```bash
pip install aerospike-py         # core
pip install aerospike-py[numpy]  # NumPy batch integration
pip install aerospike-py[otel]   # OpenTelemetry context propagation
```

Wheels include Python 3.14 and 3.14t (free-threaded, `gil_used=true`).

**Import note**: Rust/PyO3 extension. All exceptions and constants live on `aerospike_py` module directly (e.g., `aerospike_py.RecordNotFound`). No `aerospike_py.exception` submodule. Return types are NamedTuples — use `record.bins`, `record.meta.gen`. Type stubs: `src/aerospike_py/__init__.pyi`

## 1. Client Setup

```python
import aerospike_py; from aerospike_py import AsyncClient

client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()
client = aerospike_py.client(config).connect("admin", "admin")  # with auth
with aerospike_py.client(config).connect() as client: ...       # context manager
async with AsyncClient(config) as client: await client.connect() # async
```

Config: `hosts` (required), `cluster_name`, `auth_mode`, `user`, `password`, `timeout`, `idle_timeout`, `max_conns_per_node`, `tend_interval`, `use_services_alternate`, `max_concurrent_operations` (backpressure), `operation_queue_timeout_ms`. Detail: `./reference/client-config.md`

## 2. Return Types

NamedTuples from `aerospike_py.types` -- use attribute access, not index:

```python
record = client.get(key)
record.bins["name"], record.meta.gen, record.meta.ttl  # attribute access
_, meta, bins = client.get(key)                         # tuple unpacking also works
# Record(key, meta, bins) | ExistsResult(key, meta) | OperateOrderedResult(key, meta, ordered_bins)
```

Detail: `./reference/types.md`

## 3. CRUD

```python
key = ("test", "demo", "user1")
client.put(key, {"name": "Alice", "age": 30})
client.put(key, {"score": 100}, meta={"ttl": 300})
client.put(key, {"x": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
client.put(key, {"x": 1}, meta={"gen": 2}, policy={"gen": aerospike_py.POLICY_GEN_EQ})

record = client.get(key)                          # Read -> Record
record = client.select(key, ["name"])              # specific bins
result = client.exists(key)                        # ExistsResult (meta=None if missing)
client.remove(key)                                 # Delete
client.touch(key, val=300)                         # Reset TTL
client.append(key, "name", "_suffix"); client.prepend(key, "name", "prefix_")
client.increment(key, "counter", 1); client.increment(key, "score", 0.5)
client.remove_bin(key, ["temp_bin"])
```

> Async: add `await` to all I/O methods.

## 4. Error Handling

```python
try:
    record = client.get(key)
except aerospike_py.RecordNotFound: ...
except aerospike_py.BackpressureError: ...   # max_concurrent_operations exceeded
except aerospike_py.AerospikeTimeoutError: ...
except aerospike_py.AerospikeError as e: ...  # catch-all
```

Hierarchy: `AerospikeError` > `ClientError(BackpressureError)`, `ClusterError`, `AerospikeTimeoutError`, `RecordError(RecordNotFound, RecordExistsError, RecordGenerationError, FilteredOut, ...)`, `ServerError(AerospikeIndexError, QueryError, AdminError, UDFError)`

`TimeoutError`/`IndexError` aliases are removed -- use `AerospikeTimeoutError`/`AerospikeIndexError`.

Detail: `./reference/admin.md`

## 5. Batch Operations

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# batch_read -> dict[UserKey, AerospikeRecord]  (UserKey = str | int, AerospikeRecord = dict[str, Any])
records = client.batch_read(keys)  # or batch_read(keys, bins=["name"])
for user_key, bins in records.items():
    print(user_key, bins["name"])
# Missing keys are absent from dict. 2.6x faster than C client under asyncio.gather.

# batch_operate / batch_remove return BatchWriteResult (NamedTuple wrapper with .batch_records)
results = client.batch_operate(keys, [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}])
for br in results.batch_records:
    if br.result == 0 and br.record is not None: print(br.record.bins)

results = client.batch_remove(keys)
failed = [br for br in results.batch_records if br.result != 0]
```

NumPy: `batch_read(..., _dtype=np.dtype(...))` returns `NumpyBatchRecords` (NOT dict); `batch_write_numpy(data, ns, set, dtype, retry=3)` for writes with auto-retry. Detail: `./reference/read.md` | `./reference/write.md`

## 5b. Batch Write

Per-record bins (and optional per-record TTL/gen via `WriteMeta`). Different from `batch_operate` which applies same ops to all keys.

```python
records = [
    (("test", "demo", "u1"), {"name": "Alice", "age": 30}),
    (("test", "demo", "u2"), {"name": "Bob",   "age": 25}, {"ttl": 3600}),
    (("test", "demo", "u3"), {"name": "Carol", "age": 40}, {"ttl": 0, "gen": 5}),  # CAS via gen
]
result = client.batch_write(records, retry=0)  # BatchWriteResult
for br in result.batch_records:
    if br.result != 0:
        if br.in_doubt:
            ...  # write may have succeeded -- do NOT blindly retry non-idempotent ops
        else:
            ...  # safe to retry
```

`BatchRecord.in_doubt: bool` is critical for idempotency decisions. Detail: `./reference/write.md`

## 6. Operate / Operate Ordered

Atomic multi-op on a single record. CDT ops (Section 7) can be mixed in.

```python
ops = [
    {"op": aerospike_py.OPERATOR_INCR, "bin": "counter", "val": 1},
    {"op": aerospike_py.OPERATOR_READ, "bin": "counter", "val": None},
]
record = client.operate(key, ops)  # READ=1, WRITE=2, INCR=5, APPEND=9, PREPEND=10, TOUCH=11, DELETE=12
result = client.operate_ordered(key, ops)  # preserves operation order in result.ordered_bins
```

## 7. CDT Operations

```python
from aerospike_py import list_operations as lop, map_operations as mop
from aerospike_py import bit_operations as bop, hll_operations as hop

record = client.operate(key, [
    lop.list_append("mylist", "val"), lop.list_get("mylist", 0), lop.list_size("mylist"),
])
record = client.operate(key, [
    mop.map_put("mymap", "k1", "v1"),
    mop.map_get_by_key("mymap", "k1", aerospike_py.MAP_RETURN_VALUE),
])
# Bit operations (bitwise manipulation on bytes bins)
record = client.operate(key, [bop.bit_set("flags", 0, 8, b"\xff"), bop.bit_count("flags", 0, 64)])
# HyperLogLog (cardinality estimation)
record = client.operate(key, [hop.hll_add("visitors", ["u1", "u2"], 10), hop.hll_get_count("visitors")])
```

Detail: `./reference/write.md` | `./reference/constants.md`

## 8. Query & Index

```python
from aerospike_py import predicates as p
client.index_integer_create("test", "demo", "age", "age_idx")
client.index_string_create("test", "demo", "name", "name_idx")

query = client.query("test", "demo")
query.select("name", "age"); query.where(p.between("age", 20, 40))
records = query.results()     # or query.foreach(callback)
```

Predicates: `p.equals(bin, val)`, `p.between(bin, min, max)`, `p.contains(bin, idx_type, val)`

> Scan API removed -- use `Query` (no `where` clause) for full-set scan. `get_many`/`exists_many`/`select_many` removed -- use `batch_read`/`batch_operate`.

## 9. Expression Filters

Server-side filtering (Aerospike 5.2+). No secondary index required. Policy key: `"filter_expression"`.

```python
from aerospike_py import exp
expr = exp.and_(exp.gt(exp.int_bin("age"), exp.int_val(18)),
                exp.eq(exp.string_bin("status"), exp.string_val("active")))
record = client.get(key, policy={"filter_expression": expr})

# Also: exp.bin_exists("f"), exp.ttl(), exp.regex_compare(r"^u_", 0, exp.string_bin("n"))
# Variable binding: exp.let_(exp.def_("x", exp.int_bin("a")), exp.gt(exp.var("x"), exp.int_val(10)))
# Works with: get, put, batch_read, query.results, operate
```

Detail: `./reference/read.md`

## 10. Admin & Infrastructure

```python
# User management
client.admin_create_user("user1", "pass", ["read-write"])
client.admin_drop_user("user1")

# Cluster topology (sync call on both sync/async clients)
nodes = client.get_node_names()  # list[str] — NOT awaitable, always sync

# Info
results = client.info_all("namespaces")  # list[InfoNodeResult]
response = client.info_random_node("build")  # str
```

Detail: `./reference/admin.md`

## 10b. Health Check (`ping`)

```python
ok: bool = client.ping()              # sync: info("build") round-trip to a random node
ok: bool = await async_client.ping()  # async equivalent
```

Never raises -- returns `False` on failure. Use for K8s readiness probes and load-balancer health checks. Detail: `./reference/health.md`

## 11. Observability

```python
# Metrics (Prometheus text format)
aerospike_py.start_metrics_server(port=9464)        # built-in HTTP /metrics endpoint
aerospike_py.stop_metrics_server()
aerospike_py.get_metrics()                           # current metrics as string
aerospike_py.set_metrics_enabled(False)              # disable collection (~1ns atomic check overhead)
aerospike_py.is_metrics_enabled()                    # bool

# Tracing (OpenTelemetry; reads OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SERVICE_NAME)
aerospike_py.init_tracing(); aerospike_py.shutdown_tracing()

# Logging (Rust -> Python bridge)
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)  # OFF=-1,ERR=0,WARN=1,INFO=2,DBG=3,TRACE=4
aerospike_py.dropped_log_count()                     # int -- back-pressure counter (drops when sink slow)
```

Detail: `./reference/observability.md`

## 12. FastAPI Integration

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from aerospike_py import AsyncClient
import aerospike_py

@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncClient({"hosts": [("127.0.0.1", 18710)], "max_concurrent_operations": 64})
    aerospike_py.init_tracing(); await client.connect()
    app.state.aerospike = client
    yield
    await client.close(); aerospike_py.shutdown_tracing()

app = FastAPI(lifespan=lifespan)
get_client = lambda r: r.app.state.aerospike

@app.get("/records/{pk}")
async def get_record(pk: str, client: AsyncClient = Depends(get_client)):
    try:
        return (await client.get(("test", "demo", pk))).bins
    except aerospike_py.RecordNotFound:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "not found"})
```

Detail: `./reference/client-config.md` | `./reference/types.md`

## 13. Policy Reference

Detail: `./reference/policies.md` | `./reference/constants.md`
