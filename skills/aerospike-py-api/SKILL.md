---
name: aerospike-py-api
description: "MUST USE when writing any Python code with aerospike-py or aerospike_py. Rust/PyO3 library with UNCONVENTIONAL patterns — exceptions are importable both from the top-level module (aerospike_py.RecordNotFound) and from aerospike_py.exception (with TimeoutError/IndexError being deprecated aliases there), return types are NamedTuples (record.bins, record.meta.gen, NOT tuple unpacking), batch_read returns a LazyBatchRecords handle (.to_dict() for dict[UserKey, AerospikeRecord], .to_list() for request-order positional list[bins | None] collision-safe across sets, .to_numpy(np.dtype([...])) for a zero-copy structured array; handle.items()/handle[\"k\"] still work via Mapping backward-compat; the legacy _dtype= kwarg is removed), policies use module-level constants (aerospike_py.POLICY_EXISTS_CREATE_ONLY). Without this skill, code uses wrong import paths/return types and misses expression filters (exp), batch_write in_doubt retry, CDT list/map/bit/hll, ping(), backpressure, Prometheus metrics, OpenTelemetry, NumPy, and admin APIs. Triggers on: aerospike-py, aerospike_py, AsyncClient, client.ping(), batch_write, Python + Aerospike, put/get/query/batch with Aerospike."
---

## Install & Import

`pip install aerospike-py` (extras: `[numpy]`, `[otel]`). Wheels include 3.14 and 3.14t (free-threaded, `gil_used=false` — the GIL stays disabled on 3.14t, so threaded workloads scale).

**Rust/PyO3 extension — unconventional patterns**: exceptions import from `aerospike_py` directly (preferred) or `aerospike_py.exception`; constants live on the module (`aerospike_py.POLICY_EXISTS_CREATE_ONLY`); return types are NamedTuples — `record.bins`, `record.meta.gen`, `record.meta.ttl` (tuple unpacking also works). Shapes: `Record(key, meta, bins)`, `ExistsResult(key, meta)`, `OperateOrderedResult(key, meta, ordered_bins)` — `./reference/types.md`. Stubs: `src/aerospike_py/__init__.pyi`

## 1. Client Setup

```python
import aerospike_py; from aerospike_py import AsyncClient
client = aerospike_py.client({"hosts": [("127.0.0.1", 18710)]}).connect()   # sync (builder)
client = aerospike_py.client(config).connect("admin", "admin")              # with auth
async with AsyncClient(config) as client: await client.connect()            # async
```

Config keys (`hosts` required; `max_concurrent_operations` = backpressure; `cluster_name`, `auth_mode`, timeouts, pool sizing, …): `./reference/client-config.md`

## 2. CRUD

```python
key = ("test", "demo", "user1")
client.put(key, {"name": "Alice"}, meta={"ttl": 300})
client.put(key, {"x": 1}, policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
client.put(key, {"x": 1}, meta={"gen": 2}, policy={"gen": aerospike_py.POLICY_GEN_EQ})
record = client.get(key)                    # -> Record; select(key, ["name"]) for bins subset
result = client.exists(key)                 # ExistsResult (meta=None if missing)
client.remove(key); client.touch(key, val=300); client.remove_bin(key, ["temp_bin"])
client.append(key, "name", "_sfx"); client.increment(key, "counter", 1)  # offset int/float only
```

> Async: add `await` to all I/O methods. Detail: `./reference/write.md` | `./reference/read.md`

## 3. Error Handling

Catch specifics (`RecordNotFound`, `BackpressureError` = `max_concurrent_operations` exceeded, `AerospikeTimeoutError`) before the `AerospikeError` catch-all. Hierarchy: `AerospikeError` > `ClientError(BackpressureError)`, `ClusterError`, `InvalidArgError`, `AerospikeTimeoutError`, `RecordError(RecordNotFound, RecordExistsError, RecordGenerationError, FilteredOut, ...)`, `ServerError(AerospikeIndexError, QueryError, AdminError, UDFError)`. `aerospike_py.exception.TimeoutError`/`IndexError` are **deprecated aliases** (DeprecationWarning). Result-code table + batch error mapping: `./reference/admin.md`

## 4. Batch Operations

```python
lazy = client.batch_read(keys)              # LazyBatchRecords handle, NOT a dict
for user_key, bins in lazy.items(): ...     # dict-like Mapping; missing keys absent
rows = lazy.to_list()                       # request-order list[bins|None], multi-set collision-safe
arr  = lazy.to_numpy(np.dtype([...]))       # zero-copy structured array (GIL released; torch.from_numpy)
# batch_operate/batch_remove/batch_write -> BatchWriteResult; iterate .batch_records, br.result != 0 = failed
results = client.batch_operate(keys, [{"op": aerospike_py.OPERATOR_INCR, "bin": "views", "val": 1}])
# batch_write(records, retry=0): per-record bins + optional {"ttl":..,"gen":..} meta;
# br.in_doubt=True -> write MAY have applied; do NOT blindly retry non-idempotent ops
```

Legacy `_dtype=` kwarg and `as_dict()`/`merge_as_dict()` aliases are **removed**. NumPy writes: `batch_write_numpy(...)`. Detail: `./reference/read.md` | `./reference/write.md`

## 5. Operate / CDT Operations

```python
ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": "c", "val": 1},   # val int/float else TypeError
       {"op": aerospike_py.OPERATOR_READ, "bin": "c", "val": None}]
record = client.operate(key, ops)
result = client.operate_ordered(key, ops)   # order preserved in result.ordered_bins
from aerospike_py import list_operations as lop, map_operations as mop   # also bit_/hll_operations
client.operate(key, [lop.list_append("l", "v"), mop.map_get_by_key("m", "k", aerospike_py.MAP_RETURN_VALUE)])
```

`return_type` is family-validated client-side (list ops → `LIST_RETURN_*`, map ops → `MAP_RETURN_*`; wrong family → `ValueError`); bit op flags are strict too. Operator codes + all CDT helpers: `./reference/write.md` | `./reference/constants.md`

## 6. Query & Index

```python
from aerospike_py import predicates as p
client.index_integer_create("test", "demo", "age", "age_idx")   # IndexFoundError if name exists
query = client.query("test", "demo")
query.select("name", "age"); query.where(p.between("age", 20, 40))
records = query.results()     # or query.foreach(callback)
```

Predicates validated client-side at query-build (`InvalidArgError`): `p.equals`, `p.between` (integer bounds), `p.contains`. Scan API removed — use `Query` without `where`; `get_many`/`exists_many`/`select_many` removed — use `batch_read`/`batch_operate`. Detail: `./reference/read.md`

## 7. Expression Filters

Server-side filtering (Aerospike 5.2+), no secondary index required. Policy key `"filter_expression"` — works with get, put, batch_read, query.results, operate.

```python
from aerospike_py import exp
expr = exp.and_(exp.gt(exp.int_bin("age"), exp.int_val(18)),
                exp.eq(exp.string_bin("status"), exp.string_val("active")))
record = client.get(key, policy={"filter_expression": expr})
exp.regex_compare(r"^u_", aerospike_py.REGEX_NONE, exp.string_bin("n"))  # REGEX_* constants, not magic ints
```

PK regex scan: `exp.regex_compare("^aaa.*", REGEX_NONE, exp.key(exp.EXP_TYPE_STRING))` — requires `POLICY_KEY_SEND` on writes; full set scan, NOT a PK-index lookup. Variable binding: `exp.let_(exp.def_("x", ...), body)` — `cond()`/`let_()` operand counts validated client-side (`InvalidArgError`). Detail: `./reference/read.md` · Regex flags: `./reference/constants.md`

## 8. Admin, Info & Health

`client.admin_create_user("user1", "pass", ["read-write"])` (+ roles/privileges APIs) · `client.get_node_names()` (sync on BOTH clients — never awaitable) · `client.info_all("namespaces")` → `list[InfoNodeResult]` · `client.ping()` → bool, never raises (K8s readiness probes). Detail: `./reference/admin.md` | `./reference/health.md`

## 9. Observability

`start_metrics_server(port=9464)` / `get_metrics()` / `set_metrics_enabled()` (Prometheus) · `init_tracing()` / `shutdown_tracing()` (OpenTelemetry, `OTEL_*` env vars) · `set_log_level(aerospike_py.LOG_LEVEL_DEBUG)` (OFF=-1..TRACE=4; invalid → ValueError). Detail: `./reference/observability.md`

## 10. FastAPI / Policies

FastAPI patterns (lifespan + Depends, exception → HTTP-status mapping incl. `BackpressureError → 503`, `ping()` readiness, batch endpoints): use the dedicated **`aerospike-py-fastapi`** skill. Policy dicts and constants: `./reference/policies.md` | `./reference/constants.md`
