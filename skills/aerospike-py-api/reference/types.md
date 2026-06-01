# Types Reference

## Table of Contents
- [Common Type Aliases](#common-type-aliases)
- [Return Types (NamedTuple)](#return-types)
- [Policy Types (TypedDict)](#policy-types)
- [Internal Types](#internal-types)

---

## Common Type Aliases

```python
UserKey         = str | int                          # primary key value
AerospikeRecord = dict[str, Any]                     # bins dict
BatchRecords    = dict[UserKey, AerospikeRecord]     # dict shape of LazyBatchRecords.to_dict()
```

`batch_read()` returns a **`LazyBatchRecords` handle** (deferred-conversion wrapper around raw Rust results — NOT a dict, NOT a NamedTuple). Materialise via `.to_dict()` (→ `BatchRecords`) or `.to_numpy(dtype)` (→ `NumpyBatchRecords`). It also implements the dict-like Mapping protocol over a cached `to_dict()` view, so `.items()` / `["k"]` / `"k" in handle` work without `.to_dict()`. Missing keys are absent from the dict view.

**Removed (BREAKING):** the `batch_read(..., _dtype=...)` kwarg (use `.to_numpy(dtype)`); the transitional `as_dict()` / `merge_as_dict()` aliases (use `to_dict()` / `merge_to_dict()`). The old `BatchReadHandle` class was renamed `LazyBatchRecords`.

Write-style batch methods (`batch_write`, `batch_operate`, `batch_remove`, `batch_write_numpy`) return `BatchWriteResult`, a NamedTuple with `.batch_records: list[BatchRecord]` (see below).

---

## Return Types

All read operations return NamedTuple instances with named field access and tuple unpacking.
Import from `aerospike_py.types`.

### Record
`(key: AerospikeKey | None, meta: RecordMetadata | None, bins: dict[str, Any] | None)`

Returned by `get`, `select`, `operate`, `Query.results`.

| Field | Type | Description |
|-------|------|-------------|
| key | AerospikeKey \| None | Record key |
| meta | RecordMetadata \| None | Generation and TTL |
| bins | dict[str, Any] \| None | Bin values |

```python
record = client.get(key)
print(record.bins)         # attribute access
_, meta, bins = record     # tuple unpacking
```

### AerospikeKey
`(namespace: str, set_name: str, user_key: str | int | bytes | None, digest: bytes)`

| Field | Type | Description |
|-------|------|-------------|
| namespace | str | Namespace |
| set_name | str | Set name |
| user_key | str \| int \| bytes \| None | Primary key (`None` unless written with `POLICY_KEY_SEND`) |
| digest | bytes | 20-byte RIPEMD-160 digest |

### RecordMetadata
`(gen: int, ttl: int)`

| Field | Type | Description |
|-------|------|-------------|
| gen | int | Record generation (write count, used for optimistic locking) |
| ttl | int | Seconds until expiration |

### BatchRecord
`(key: AerospikeKey | None, result: int, record: Record | None, in_doubt: bool = False)`

Per-record result from write-style batch operations (`batch_write`, `batch_operate`, `batch_remove`, `batch_write_numpy`). `result` is 0 on success.

| Field | Type | Description |
|-------|------|-------------|
| key | AerospikeKey \| None | Record key |
| result | int | Per-record result code (0 = success) |
| record | Record \| None | Record data (`None` if failed) |
| in_doubt | bool | `True` if the write may have completed despite the error (e.g., timeout after send). Check before retrying to avoid duplicates with non-idempotent ops. |

### LazyBatchRecords

Returned by sync **and** async `batch_read()`. A zero-conversion handle that wraps the raw Rust results; materialisation is deferred to explicit method calls.

| Method / Operator | Returns | Description |
|-------------------|---------|-------------|
| `lazy_records.to_dict()` | `dict[UserKey, AerospikeRecord]` (`= BatchRecords`) | Materialise as `dict[user_key, bins_dict]`. Excludes digest-only and failed records. |
| `lazy_records.to_numpy(dtype)` | `NumpyBatchRecords` | Materialise as a structured array. `dtype` **must be a real `np.dtype` object** (e.g. `np.dtype([("score","i4")])`). The per-record fill loop runs with the GIL released (`py.detach`), so sibling work (torch inference, other asyncio tasks) can hold the GIL while the buffer fills. |
| `lazy_records.batch_records` | `list[BatchRecord]` | Compat path: lazy NamedTuple conversion. Includes digest-only and failed records. |
| `lazy_records.items()` / `keys()` / `values()` / `get()` | dict views | Dict-style — same semantics as the cached `to_dict()`. |
| `lazy_records[user_key]` / `user_key in lazy_records` | dict access | Dict-like backward compat. |
| `len(lazy_records)` | `int` | Dict-view cardinality (successful reads with a `user_key`); pure-Rust count, no PyDict build. |
| `lazy_records.iter_records()` | `Iterator[BatchRecord]` | Iterate every record (including digest-only and failed) in insertion order. |
| `lazy_records.all_user_keys()` | `list[UserKey \| None]` | Every record's `user_key` in request order (positionally aligned with `batch_records` / `NumpyBatchRecords`; `None` for digest-only requests). |
| `lazy_records.found_count()` | `int` | Count of successful records (no conversion needed). |
| `lazy_records.release_cache()` | `None` | Drop the cached `to_dict()` PyDict, keeping raw records. |

`merge_to_dict([h1, h2, ...])` is a static single-GIL merge. (No `as_dict`/`merge_as_dict`/`raw_user_keys` — those names do not exist.)

```python
lazy_records = client.batch_read(keys)                       # LazyBatchRecords handle

# Dict path
for user_key, bins in lazy_records.items():                  # dict-like
    print(user_key, bins["name"])
records = lazy_records.to_dict()                             # BatchRecords

# NumPy / torch path (zero-copy)
import numpy as np
import torch
np_batch = lazy_records.to_numpy(np.dtype([("score", "i4")]))
tensor = torch.from_numpy(np_batch.batch_records["score"])
```

### BatchWriteResult
`(batch_records: list[BatchRecord])`

NamedTuple returned by all write-style batch methods: `batch_write`, `batch_operate`, `batch_remove`, `batch_write_numpy`. Iterate `result.batch_records` and check each `BatchRecord.result` (and `.in_doubt` for write retry decisions).

```python
result = client.batch_write([(key, bins), (key2, bins2, {"ttl": 60})])
for br in result.batch_records:
    if br.result != 0 and not br.in_doubt:
        ...  # safe to retry
```

### ExistsResult
`(key: AerospikeKey | None, meta: RecordMetadata | None)`

Returned by `exists`. `meta` is `None` if the record does not exist.

| Field | Type | Description |
|-------|------|-------------|
| key | AerospikeKey \| None | Record key |
| meta | RecordMetadata \| None | `None` if record does not exist |

### OperateOrderedResult
`(key: AerospikeKey | None, meta: RecordMetadata | None, ordered_bins: list[BinTuple])`

Returned by `operate_ordered`. Preserves operation order in results.

| Field | Type | Description |
|-------|------|-------------|
| key | AerospikeKey \| None | Record key |
| meta | RecordMetadata \| None | Record metadata |
| ordered_bins | list[BinTuple] | Ordered operation results |

### BinTuple
`(name: str, value: Any)`

Single bin name-value pair used in `OperateOrderedResult.ordered_bins`.

| Field | Type | Description |
|-------|------|-------------|
| name | str | Bin name |
| value | Any | Bin value |

### InfoNodeResult
`(node_name: str, error_code: int, response: str)`

Returned by `info_all`. One result per cluster node.

| Field | Type | Description |
|-------|------|-------------|
| node_name | str | Cluster node name |
| error_code | int | 0 on success |
| response | str | Info response string |

### Return Type Quick Reference

| Method | Return Type |
|--------|-------------|
| `get()`, `select()` | `Record` |
| `exists()` | `ExistsResult` |
| `operate()` | `Record` |
| `operate_ordered()` | `OperateOrderedResult` |
| `info_all()` | `list[InfoNodeResult]` |
| `batch_read()` | `LazyBatchRecords` — call `.to_dict()` for `BatchRecords` shape, `.to_numpy(np.dtype([...]))` for `NumpyBatchRecords` |
| `batch_write()`, `batch_operate()`, `batch_remove()`, `batch_write_numpy()` | `BatchWriteResult` (NamedTuple, `.batch_records: list[BatchRecord]`) |
| `ping()` | `bool` |
| `Query.results()` | `list[Record]` |

---

## Policy Types

All fields are optional (`total=False`) unless noted. Import from `aerospike_py.types`.

### ReadPolicy

Used by: `get()`, `select()`, `exists()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 1000 | Total transaction timeout (ms) |
| max_retries | int | 2 | Max retry attempts |
| sleep_between_retries | int | 0 | Sleep between retries (ms) |
| filter_expression | Any | | Expression filter |
| replica | int | POLICY_REPLICA_SEQUENCE | Replica policy (`POLICY_REPLICA_*`) |
| read_mode_ap | int | POLICY_READ_MODE_AP_ONE | AP read mode (`POLICY_READ_MODE_AP_*`) |

### WritePolicy

Used by: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 1000 | Total transaction timeout (ms) |
| max_retries | int | 0 | Max retry attempts |
| durable_delete | bool | false | Durable delete (Enterprise) |
| key | int | POLICY_KEY_DIGEST | Key send policy (`POLICY_KEY_*`) |
| exists | int | POLICY_EXISTS_IGNORE | Record exists policy (`POLICY_EXISTS_*`) |
| gen | int | POLICY_GEN_IGNORE | Generation policy (`POLICY_GEN_*`) |
| commit_level | int | POLICY_COMMIT_LEVEL_ALL | Commit level (`POLICY_COMMIT_LEVEL_*`) |
| ttl | int | 0 | Record TTL in seconds |
| filter_expression | Any | | Expression filter |

### WriteMeta

Used by: `put()`, `remove()`, `touch()`, `operate()` etc. as `meta` parameter, and by `batch_write()` as the optional 3rd tuple element per record. `gen` is honored by `batch_write` for per-record CAS.

| Field | Type | Description |
|-------|------|-------------|
| gen | int | Expected generation for CAS (`POLICY_GEN_EQ`) |
| ttl | int | Record TTL in seconds |

### BatchPolicy

Used by: `batch_read()`, `batch_operate()`, `batch_remove()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 1000 | Total transaction timeout (ms) |
| max_retries | int | 2 | Max retry attempts |
| filter_expression | Any | | Expression filter |

### QueryPolicy

Used by: `Query.results()`, `Query.foreach()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 0 | Total timeout (0 = no limit) |
| max_retries | int | 2 | Max retry attempts |
| max_records | int | 0 | Max records to return (0 = all) |
| records_per_second | int | 0 | Rate limit (0 = unlimited) |
| filter_expression | Any | | Expression filter |

### AdminPolicy

Used by: all `admin_*` methods, index operations, `truncate()`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| timeout | int | 1000 | Admin operation timeout (ms) |

### Privilege

Used by: `admin_create_role()`, `admin_grant_privileges()`, `admin_revoke_privileges()`

| Field | Type | Description |
|-------|------|-------------|
| code | int | Privilege code (`PRIV_*`) |
| ns | str | Namespace scope (empty = global) |
| set | str | Set scope (empty = namespace-wide) |

### UserInfo (all required)

Returned by: `admin_query_user_info()`, `admin_query_users_info()`

| Field | Type | Description |
|-------|------|-------------|
| user | str | Username |
| roles | list[str] | Assigned role names |
| conns_in_use | int | Active connection count |

### RoleInfo (all required)

Returned by: `admin_query_role()`, `admin_query_roles()`

| Field | Type | Description |
|-------|------|-------------|
| name | str | Role name |
| privileges | list[Privilege] | Granted privileges |
| allowlist | list[str] | Allowed IP addresses |
| read_quota | int | Read quota |
| write_quota | int | Write quota |

---

## Internal Types

Import from `aerospike_py._types`.

### Operation

`dict[str, Any]` -- Operation dict for `client.operate()` / `client.operate_ordered()`.

Required keys:
- `op` (int): Operation code -- `OPERATOR_READ`, `OPERATOR_WRITE`, `OPERATOR_INCR`, `OPERATOR_APPEND`, `OPERATOR_PREPEND`, `OPERATOR_TOUCH`, `OPERATOR_DELETE`, or CDT codes (1000+).
- `bin` (str): Bin name to operate on (non-empty).
- `val` (Any): Value for write operations; `None` for read ops. For `OPERATOR_INCR`, `val` must be `int`/`float` (else `TypeError`).

Optional keys (CDT operations):
- `return_type` (int): `LIST_RETURN_*` (list ops) or `MAP_RETURN_*` (map ops); wrong-family/out-of-range → `ValueError`.
- `list_policy` (ListPolicy): Policy for list CDT operations.
- `map_policy` (MapPolicy): Policy for map CDT operations.
- `hll_policy` (HLLPolicy): Policy for HyperLogLog CDT operations.
- `bit_policy` (int): Bit write flags for bitwise CDT operations (`BIT_WRITE_*`).

Built by helper modules: `list_operations`, `map_operations`, `hll_operations`, `bit_operations`.

### ListPolicy

| Field | Type | Description |
|-------|------|-------------|
| order | int | `LIST_UNORDERED` or `LIST_ORDERED` |
| flags | int | `LIST_WRITE_*` flags |

### MapPolicy

| Field | Type | Description |
|-------|------|-------------|
| order | int | `MAP_UNORDERED`, `MAP_KEY_ORDERED`, `MAP_KEY_VALUE_ORDERED` |
| write_mode | int | `MAP_UPDATE`, `MAP_UPDATE_ONLY`, `MAP_CREATE_ONLY` |

### HLLPolicy

| Field | Type | Description |
|-------|------|-------------|
| flags | int | `HLL_WRITE_*` flags |
