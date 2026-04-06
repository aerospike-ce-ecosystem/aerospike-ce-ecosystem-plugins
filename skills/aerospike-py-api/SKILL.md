---
name: aerospike-py-api
description: "MUST USE when writing any Python code with aerospike-py or aerospike_py. This is a Rust/PyO3 library with UNCONVENTIONAL patterns that differ from typical Python clients — exceptions live on the module (aerospike_py.RecordNotFound, NOT aerospike_py.exception.RecordNotFound), return types are NamedTuples (record.bins, record.meta.gen, NOT tuple unpacking), and policies use module-level constants (aerospike_py.POLICY_EXISTS_CREATE_ONLY). Without this skill, code will use wrong import paths, wrong return type patterns, and miss critical features like expression filters (exp module), batch operations, CDT list/map/bit/hll, operate_ordered, backpressure (max_concurrent_operations), Prometheus get_metrics(), OpenTelemetry tracing, NumPy integration, and admin APIs. Triggers on: aerospike-py, aerospike_py, AsyncClient, Python + Aerospike, put/get/query/batch with Aerospike."
---

## Installation

```bash
pip install aerospike-py         # core
pip install aerospike-py[numpy]  # NumPy batch integration
pip install aerospike-py[otel]   # OpenTelemetry context propagation
```

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

Detail: `./reference/admin.md`

## 5. Batch Operations

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# All batch operations return BatchRecords (same container type)
batch = client.batch_read(keys)  # or batch_read(keys, bins=["name"])
for br in batch.batch_records:
    if br.result == 0 and br.record is not None: print(br.record.bins)

records = [(k, {"name": f"user_{i}", "score": i * 10}) for i, k in enumerate(keys)]
results = client.batch_write(records, retry=3)  # per-record bins, auto-retry transient failures
for br in results.batch_records:
    if br.result != 0: print(f"Failed: {br.key}, in_doubt={br.in_doubt}")

results = client.batch_operate(keys, [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}])
for br in results.batch_records:
    if br.result == 0 and br.record is not None: print(br.record.bins)

results = client.batch_remove(keys)
failed = [br for br in results.batch_records if br.result != 0]
```

NumPy: `batch_read(..., _dtype=np.dtype(...))` for zero-copy arrays; `batch_write_numpy(data, ns, set, dtype, retry=3)` for writes with auto-retry. Detail: `./reference/read.md` | `./reference/write.md`

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

## 11. Observability

```python
aerospike_py.start_metrics_server(port=9464)       # Prometheus /metrics endpoint
aerospike_py.get_metrics()                          # Prometheus text format string
aerospike_py.init_tracing(); aerospike_py.shutdown_tracing()  # OpenTelemetry (OTEL_* env vars)
aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_DEBUG)      # OFF=-1,ERR=0,WARN=1,INFO=2,DBG=3,TRACE=4
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
