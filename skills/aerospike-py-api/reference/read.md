# Read Reference

## Table of Contents
- [Read Operations](#read-operations)
- [Query & Secondary Index](#query--secondary-index)
- [Expression Filters](#expression-filters)
- [NumPy Batch Read](#numpy-batch-read)

---

## Read Operations

### Keys

Every record is identified by a key tuple: `(namespace, set, primary_key)`.

```python
key = ("test", "demo", "user1")      # string PK
key = ("test", "demo", 12345)         # integer PK
key = ("test", "demo", b"\x01\x02")   # bytes PK
```

### get(key, policy=None) -> Record

Read all bins of a record.

```python
from aerospike_py import Record

record: Record = client.get(key)
print(record.bins)       # {"name": "Alice", "age": 30}
print(record.meta.gen)   # 1
print(record.meta.ttl)   # 2591998

# Tuple unpacking (backward compat)
_, meta, bins = client.get(key)

# Async
record = await async_client.get(key)
```

### select(key, bins, policy=None) -> Record

Read specific bins only.

```python
record = client.select(key, ["name"])
# record.bins = {"name": "Alice"}
```

### exists(key, policy=None) -> ExistsResult

Check record existence (returns metadata only, no bin data).

```python
from aerospike_py import ExistsResult

result: ExistsResult = client.exists(key)
if result.meta is not None:
    print(f"gen={result.meta.gen}")
```

### batch_read(keys, bins=None, policy=None) -> LazyBatchRecords

Read multiple records in a single network call. **Returns a `LazyBatchRecords` handle** that wraps the raw Rust results — conversion is deferred to explicit method calls on the handle (the async future itself resolves with near-zero GIL cost):

- `lazy_records.to_dict()` → `dict[UserKey, AerospikeRecord]` (missing / failed records absent)
- `lazy_records.to_numpy(dtype)` → `NumpyBatchRecords` (zero-copy structured array — the per-record buffer fill runs with the GIL released via `py.detach`)
- `lazy_records.to_list()` → `list[bins_dict | None]` in request order (`None` at miss/failure; not cached). Collision-safe across sets, where `to_dict()` keeps only one record per `user_key`.
- `lazy_records.batch_records` → `list[BatchRecord]` (compat — includes digest-only and failed records)

`LazyBatchRecords` also implements the dict-like Mapping protocol so existing dict-style code keeps working without explicit `.to_dict()`:

```python
keys = [("test", "demo", f"user_{i}") for i in range(10)]

# All bins — handle is dict-like (backed by a lazy + cached to_dict view)
lazy_records = client.batch_read(keys)
for user_key, bins in lazy_records.items():
    print(user_key, bins["name"])

# Or call .to_dict() explicitly
records: dict[str | int, dict[str, Any]] = lazy_records.to_dict()

# Specific bins
lazy_records = client.batch_read(keys, bins=["name", "age"])

# Existence check (empty bins) -- handle is still dict-like; missing keys absent
lazy_records = client.batch_read(keys, bins=[])

# Positional list -- aligned 1:1 with `keys`; None at miss/failure (collision-safe across sets)
results = client.batch_read(keys, bins=["name"]).to_list()
for key, bins in zip(keys, results):
    if bins is not None:        # bins == {} for a header-only hit, None for miss/failure
        print(key, bins["name"])

# Async
lazy_records = await async_client.batch_read(keys, bins=["name", "age"])
for user_key, bins in lazy_records.items():
    ...

# NumPy zero-copy: dtype MUST be a np.dtype object (list/string not auto-promoted)
import numpy as np
dtype = np.dtype([("score", "i4")])
np_batch = client.batch_read(keys).to_numpy(dtype)
np_batch.batch_records["score"].mean()                  # columnar view
import torch
tensor = torch.from_numpy(np_batch.batch_records["score"])   # O(1) pointer share
```

**Removed / renamed (BREAKING):**

- `batch_read(..., _dtype=...)` kwarg is **gone** — use `batch_read(...).to_numpy(dtype)`.
- `BatchReadHandle` renamed to `LazyBatchRecords`. The transitional `as_dict()` / `merge_as_dict()` aliases were **removed** — use `to_dict()` / `merge_to_dict()`.

Note: `batch_operate`, `batch_remove`, `batch_write`, and `batch_write_numpy` return `BatchWriteResult` (a NamedTuple wrapping `list[BatchRecord]`) — only `batch_read` returns the `LazyBatchRecords` handle.

### ReadPolicy

| Key | Type | Description |
|-----|------|-------------|
| `socket_timeout` | int | Socket idle timeout (ms) |
| `total_timeout` | int | Total transaction timeout (ms) |
| `max_retries` | int | Maximum retry attempts |
| `sleep_between_retries` | int | Sleep between retries (ms) |
| `filter_expression` | Expr | Expression filter |
| `replica` | int | Replica algorithm |
| `read_mode_ap` | int | Read mode for AP namespaces |

### Tips

- **Batch size**: 100-5,000 keys per batch is optimal. Very large batches may timeout.
- **Timeouts**: Increase `total_timeout` for large batch operations.
- **Error handling**: Individual batch records can fail independently. Always check `br.record` for `None`.

---

## Query & Secondary Index

### Index Management

| Function | Description |
|----------|-------------|
| `index_integer_create(ns, set, bin, name)` | Create integer secondary index |
| `index_string_create(ns, set, bin, name)` | Create string secondary index |
| `index_geo2dsphere_create(ns, set, bin, name)` | Create geospatial secondary index |
| `index_remove(ns, name)` | Remove secondary index |

```python
client.index_integer_create("test", "users", "age", "users_age_idx")
client.index_string_create("test", "users", "city", "users_city_idx")
client.index_remove("test", "users_age_idx")
```

### Query Builder

```python
from aerospike_py import predicates, Record

query = client.query("test", "users")
query.select("name", "age")           # select specific bins
query.where(predicates.between("age", 25, 35))  # set predicate

records: list[Record] = query.results()          # collect all results
query.foreach(callback)                           # iterate with callback
```

### Callback Iteration

`query.foreach(cb)` calls `cb(record)` per result. **Return `False` from the callback to stop iteration early** (library-specific).

### Predicates

Import: `from aerospike_py import predicates`

| Function | Description |
|----------|-------------|
| `equals(bin, val)` | Equality match. `val` must be `int`/`str`/`bytes` (float/bool → `InvalidArgError`) |
| `between(bin, min, max)` | Range (inclusive). Bounds must be integers (float/str → `InvalidArgError`) |
| `contains(bin, idx_type, val)` | List/map contains. `idx_type` must be an `INDEX_TYPE_*` constant (else `InvalidArgError`) |
| `geo_within_geojson_region(bin, geojson)` | Points in region |
| `geo_within_radius(bin, lat, lng, radius)` | Points in circle (meters) |
| `geo_contains_geojson_point(bin, geojson)` | Regions containing point |

> **Validation (raised at query-build, client-side):** the type/range guards above, plus empty bin names in any predicate, `query.select()`, or expression bin accessor → `InvalidArgError`.
> **Geo predicates** emit a `FutureWarning` and raise `ClientError` at execution time (not yet supported).

Geo predicate args: `geo_within_geojson_region(bin, geojson_str)`, `geo_within_radius(bin, lat, lng, radius_m)`, `geo_contains_geojson_point(bin, geojson_str)`. (Not yet supported — see note above.)

---

## Expression Filters

Server-side filtering (Aerospike Server >= 5.2). No secondary index required.
Import: `from aerospike_py import exp`

All functions return `Expr` (dict with `__expr__` key). Pass to any read/write/batch/query policy:

```python
policy = {"filter_expression": expr}
```

### Value Constructors

| Function | Description |
|----------|-------------|
| `int_val(val)` | Integer constant (64-bit) |
| `float_val(val)` | Float constant (64-bit) |
| `string_val(val)` | String constant |
| `bool_val(val)` | Boolean constant |
| `blob_val(val)` | Bytes constant |
| `list_val(val)` | List constant |
| `map_val(val)` | Map/dict constant |
| `geo_val(val)` | GeoJSON string |
| `nil()` | Null value |
| `infinity()` | Infinity (range upper bound) |
| `wildcard()` | Wildcard (matches any) |

### Bin Accessors

| Function | Description |
|----------|-------------|
| `int_bin(name)` | Read integer bin |
| `float_bin(name)` | Read float bin |
| `string_bin(name)` | Read string bin |
| `bool_bin(name)` | Read boolean bin |
| `blob_bin(name)` | Read bytes bin |
| `list_bin(name)` | Read list bin |
| `map_bin(name)` | Read map bin |
| `geo_bin(name)` | Read geo bin |
| `hll_bin(name)` | Read HyperLogLog bin |
| `bin_exists(name)` | Check bin exists (returns bool expr) |
| `bin_type(name)` | Get bin particle type |

### Record Metadata

| Function | Description |
|----------|-------------|
| `key(exp_type)` | Record primary key (use `EXP_TYPE_*` constant) |
| `key_exists()` | Check if key was stored in record metadata |
| `set_name()` | Record set name |
| `record_size()` | Record size in bytes (server 7.0+) |
| `last_update()` | Last update time (nanoseconds since epoch) |
| `since_update()` | Time since last update (milliseconds) |
| `void_time()` | Record expiration time (nanoseconds since epoch) |
| `ttl()` | Record TTL in seconds |
| `is_tombstone()` | Check if tombstone record |
| `digest_modulo(modulo)` | Key digest mod N (for sampling) |

Type constants for `key(exp_type)`: `EXP_TYPE_NIL`(0), `EXP_TYPE_BOOL`(1), `EXP_TYPE_INT`(2), `EXP_TYPE_STRING`(3), `EXP_TYPE_LIST`(4), `EXP_TYPE_MAP`(5), `EXP_TYPE_BLOB`(6), `EXP_TYPE_FLOAT`(7), `EXP_TYPE_GEO`(8), `EXP_TYPE_HLL`(9).

### Comparison

All take `(left, right)` and return a boolean expression.

| Function | Operator |
|----------|----------|
| `eq(left, right)` | `==` |
| `ne(left, right)` | `!=` |
| `gt(left, right)` | `>` |
| `ge(left, right)` | `>=` |
| `lt(left, right)` | `<` |
| `le(left, right)` | `<=` |

### Logical

| Function | Description |
|----------|-------------|
| `and_(*exprs)` | Logical AND (variadic) |
| `or_(*exprs)` | Logical OR (variadic) |
| `not_(expr)` | Logical NOT |
| `xor_(*exprs)` | Logical XOR (variadic) |

### Numeric

| Function | Description |
|----------|-------------|
| `num_add(*exprs)` | Sum (variadic) |
| `num_sub(*exprs)` | Subtract (variadic) |
| `num_mul(*exprs)` | Multiply (variadic) |
| `num_div(*exprs)` | Divide (variadic) |
| `num_mod(numerator, denominator)` | Modulo |
| `num_pow(base, exponent)` | Power |
| `num_log(num, base)` | Logarithm |
| `num_abs(value)` | Absolute value |
| `num_floor(num)` | Floor |
| `num_ceil(num)` | Ceiling |
| `to_int(num)` | Convert to integer |
| `to_float(num)` | Convert to float |
| `min_(*exprs)` | Minimum (variadic) |
| `max_(*exprs)` | Maximum (variadic) |

### Integer Bitwise

| Function | Description |
|----------|-------------|
| `int_and(*exprs)` | Bitwise AND (variadic) |
| `int_or(*exprs)` | Bitwise OR (variadic) |
| `int_xor(*exprs)` | Bitwise XOR (variadic) |
| `int_not(expr)` | Bitwise NOT |
| `int_lshift(value, shift)` | Left shift |
| `int_rshift(value, shift)` | Logical right shift |
| `int_arshift(value, shift)` | Arithmetic right shift |
| `int_count(expr)` | Bit count (popcount) |
| `int_lscan(value, search)` | Scan from MSB for bit value |
| `int_rscan(value, search)` | Scan from LSB for bit value |

### Pattern Matching

| Function | Description |
|----------|-------------|
| `regex_compare(regex, flags, bin_expr)` | Regex match on string expression |
| `geo_compare(left, right)` | Geospatial contains/within comparison |

`regex_compare` flags are exposed as module-level constants on `aerospike_py`
(values mirror POSIX `regex.h`):

| Constant | Value | Meaning |
|----------|-------|---------|
| `REGEX_NONE` | 0 | Defaults |
| `REGEX_EXTENDED` | 1 | POSIX extended syntax |
| `REGEX_ICASE` | 2 | Case-insensitive |
| `REGEX_NOSUB` | 4 | Don't report match position |
| `REGEX_NEWLINE` | 8 | `.` doesn't match newline |

Combine with `|`: `REGEX_ICASE | REGEX_NEWLINE`. Avoid passing magic integers.

### Control Flow

| Function | Description |
|----------|-------------|
| `cond(*exprs)` | Conditional: `cond(bool1, val1, bool2, val2, ..., default)`. Requires odd operand count ≥ 3 (else `InvalidArgError`) |
| `var(name)` | Variable reference |
| `def_(name, value)` | Variable definition (used inside `let_`) |
| `let_(*exprs)` | Variable binding scope: `let_(def_("x", ...), ..., body_expr)`. Requires ≥ 2 operands (else `InvalidArgError`) |

> Variadic ops (`and_`/`or_`/`xor_`, `num_add`/`sub`/`mul`/`div`, `min_`/`max_`, `int_and`/`or`/`xor`) require ≥ 1 operand — an empty call (e.g. `exp.and_()`) raises `InvalidArgError`.

### Patterns

```python
from aerospike_py import exp

# Comparison + logic — age > 18 AND status == "active"
expr = exp.and_(exp.gt(exp.int_bin("age"), exp.int_val(18)),
                exp.eq(exp.string_bin("status"), exp.string_val("active")))

# Variable binding: let_(def_(name, value), ..., body)
expr = exp.let_(exp.def_("total", exp.num_add(exp.int_bin("a"), exp.int_bin("b"))),
                exp.gt(exp.var("total"), exp.int_val(100)))

# Conditional: cond(cond1, val1, ..., default) — odd count ≥ 3
expr = exp.cond(exp.gt(exp.int_bin("score"), exp.int_val(90)), exp.string_val("A"),
                exp.string_val("B"))  # default

# Metadata: expiring within 1h / ~10% sample
exp.lt(exp.ttl(), exp.int_val(3600))
exp.eq(exp.digest_modulo(10), exp.int_val(0))
```

Pass to any read/write/batch/query policy: `policy={"filter_expression": expr}` (works with `get`, `put`, `batch_read`, `query.results`, `operate`).

#### PK Regex Filter Scan

Filter records by a regex match on the **user key** (PK). Equivalent to
the Java client's `Exp.regexCompare(pattern, RegexFlag.NONE, Exp.key(Exp.Type.STRING))`.

```python
import aerospike_py
from aerospike_py import exp

# Records must be written with POLICY_KEY_SEND so the user key is stored.
client.put(("test", "users", "aaa001"), {"v": 1},
           policy={"key": aerospike_py.POLICY_KEY_SEND})

expr = exp.regex_compare(
    "^aaa.*",
    aerospike_py.REGEX_NONE,
    exp.key(exp.EXP_TYPE_STRING),
)
records = client.query("test", "users").results(
    policy={"filter_expression": expr})
for r in records:
    print(r.key.user_key, r.bins)
```

Operational notes (library-specific gotchas):

- **Full set scan + server-side filter**, NOT a primary-index lookup — Aerospike's primary index keys on the digest, not the user-key string (no PK B-tree range scan).
- Records written without `POLICY_KEY_SEND` have no stored user key and never match a `key()` expression (scan returns empty).
- For hot-path prefix lookups, denormalize a fixed-width prefix bin and `INDEX_STRING` it, then [`predicates.equals`](#predicates) — Aerospike string SI is equality-only (no range/prefix).

---

## NumPy Batch Read

Zero-copy structured-array reads via Rust. Requires `numpy >= 2.0` (`pip install aerospike-py[numpy]`). Numeric/fixed-bytes bins only — 5-10x faster than dict `batch_read` above ~10K records.

`batch_read(...).to_numpy(dtype)` → `NumpyBatchRecords`. Each dtype field maps to a bin name. **`dtype` must be a real `np.dtype` object** — list-of-tuples / dtype strings are NOT auto-promoted (wrap with `np.dtype(...)`). The per-record fill runs with the GIL released (`py.detach`) — pair with `torch.from_numpy(...)` for an O(1) hand-off.

```python
dtype = np.dtype([("score", "f8"), ("count", "i4"), ("tag", "S8")])
result = client.batch_read(keys, bins=["score", "count", "tag"]).to_numpy(dtype)
```

**Supported dtype kinds:** `i`/`u` → Integer, `f` → Float, `S` → String (truncated), `V` → Blob (truncated). Unicode `U`, object `O`, datetime `M`/`m` are **not supported**.

**`NumpyBatchRecords`** attributes: `.batch_records` (structured array), `.meta` (`(gen, ttl)` array), `.result_codes` (`int32`, 0=success). Supports `.get(key)`, `len()`, `key in`, iteration. **Gotcha:** missing/failed reads leave their row at the dtype zero value — mask with `result.result_codes == 0` before any aggregation. `pd.DataFrame(result.batch_records)` is zero-copy for numeric data.
