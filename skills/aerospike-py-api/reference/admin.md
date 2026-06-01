# Admin Reference

## Table of Contents
- [User Management](#user-management)
- [Role Management](#role-management)
- [Privilege Constants](#privilege-constants)
- [UDF (Lua)](#udf-lua)
- [Info & Truncate](#info--truncate)
- [Error Handling](#error-handling)
- [Exception Hierarchy](#exception-hierarchy)

---

## User Management

Requires a security-enabled Aerospike server.

| Method | Signature | Description |
|--------|-----------|-------------|
| admin_create_user | (username, password, roles, policy=None) | Create user |
| admin_drop_user | (username, policy=None) | Delete user |
| admin_change_password | (username, password, policy=None) | Change password |
| admin_grant_roles | (username, roles, policy=None) | Add roles to user |
| admin_revoke_roles | (username, roles, policy=None) | Remove roles from user |
| admin_query_user_info | (username, policy=None) -> dict | Get user info |
| admin_query_users_info | (policy=None) -> list[dict] | Get all users |

```python
import aerospike_py as aerospike

client.admin_create_user("alice", "secure_password", ["read-write"])
client.admin_change_password("alice", "new_password")
client.admin_grant_roles("alice", ["sys-admin"])
client.admin_revoke_roles("alice", ["read-write"])

user = client.admin_query_user_info("alice")   # UserInfo dict
users = client.admin_query_users_info()         # list[UserInfo]

client.admin_drop_user("alice")
```

### UserInfo dict

| Field | Type | Description |
|-------|------|-------------|
| user | str | Username |
| roles | list[str] | Assigned role names |
| conns_in_use | int | Active connection count |

---

## Role Management

| Method | Signature | Description |
|--------|-----------|-------------|
| admin_create_role | (role, privileges, policy=None) | Create role |
| admin_drop_role | (role, policy=None) | Delete role |
| admin_grant_privileges | (role, privileges, policy=None) | Add privileges to role |
| admin_revoke_privileges | (role, privileges, policy=None) | Remove privileges from role |
| admin_query_role | (role, policy=None) -> dict | Get role info |
| admin_query_roles | (policy=None) -> list[dict] | Get all roles |
| admin_set_whitelist | (role, whitelist, policy=None) | Set IP allowlist |
| admin_set_quotas | (role, read_quota, write_quota, policy=None) | Set rate limits |

```python
import aerospike_py as aerospike

# Create role with namespace/set-scoped privileges
client.admin_create_role("data_reader", [
    {"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"},
])

# Create role with global privileges
client.admin_create_role("full_admin", [
    {"code": aerospike.PRIV_SYS_ADMIN},
    {"code": aerospike.PRIV_USER_ADMIN},
])

# Grant / revoke privileges
client.admin_grant_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])
client.admin_revoke_privileges("data_reader", [
    {"code": aerospike.PRIV_WRITE, "ns": "test", "set": "demo"},
])

# Whitelist and quotas
client.admin_set_whitelist("data_reader", ["10.0.0.0/8", "192.168.1.0/24"])
client.admin_set_quotas("data_reader", read_quota=1000, write_quota=500)

# Query / drop
role = client.admin_query_role("data_reader")   # RoleInfo dict
roles = client.admin_query_roles()               # list[RoleInfo]
client.admin_drop_role("data_reader")
```

### Privilege dict format

```python
{"code": aerospike.PRIV_READ}                              # Global
{"code": aerospike.PRIV_READ, "ns": "test"}                # Namespace-scoped
{"code": aerospike.PRIV_READ, "ns": "test", "set": "demo"} # Namespace + set-scoped
```

### RoleInfo dict

| Field | Type | Description |
|-------|------|-------------|
| name | str | Role name |
| privileges | list[Privilege] | Granted privileges |
| allowlist | list[str] | Allowed IP addresses |
| read_quota | int | Read quota |
| write_quota | int | Write quota |

### AdminPolicy

| Field | Type | Description |
|-------|------|-------------|
| timeout | int | Admin operation timeout (ms) |

---

## Privilege Constants

| Constant | Value | Description |
|----------|-------|-------------|
| PRIV_USER_ADMIN | 0 | User management |
| PRIV_SYS_ADMIN | 1 | System admin |
| PRIV_DATA_ADMIN | 2 | Data management (truncate, index) |
| PRIV_UDF_ADMIN | 3 | UDF management |
| PRIV_SINDEX_ADMIN | 4 | Secondary index management |
| PRIV_READ | 10 | Read records |
| PRIV_READ_WRITE | 11 | Read and write |
| PRIV_READ_WRITE_UDF | 12 | Read, write, and UDF |
| PRIV_WRITE | 13 | Write records |
| PRIV_TRUNCATE | 14 | Truncate operations |

---

## UDF (Lua)

| Method | Signature | Description |
|--------|-----------|-------------|
| udf_put | (filename, udf_type=0, policy=None) | Register a Lua UDF |
| apply | (key, module, function, args=None, policy=None) -> Any | Execute UDF on a record |
| udf_remove | (module, policy=None) | Remove a registered UDF |

```python
# Register
client.udf_put("counter.lua")

# Execute on a record
key = ("test", "demo", "counter1")
result = client.apply(key, "counter", "increment", ["count", 5])  # 5
result = client.apply(key, "counter", "increment", ["count", 3])  # 8

# Remove
client.udf_remove("counter")
```

**Async:**

```python
await client.udf_put("counter.lua")
result = await client.apply(key, "counter", "increment", ["count", 1])
await client.udf_remove("counter")
```

Notes:
- Lua is the only supported UDF language
- UDF changes take a few seconds to propagate to all nodes
- Keep UDFs simple for best performance

---

## Cluster Topology

| Method | Signature | Description |
|--------|-----------|-------------|
| get_node_names | () -> list[str] | Return node name list. **Sync on both Client and AsyncClient** (lock-free, no I/O). |

```python
nodes = client.get_node_names()          # sync client
nodes = async_client.get_node_names()    # async client — NOT awaitable, always sync
```

## Info & Truncate

| Method | Signature | Description |
|--------|-----------|-------------|
| info_all | (command, policy=None) -> list[InfoNodeResult] | Send info command to all nodes |
| info_random_node | (command, policy=None) -> str | Send info command to one random node |
| truncate | (namespace, set_name, nanos=0, policy=None) | Truncate a set or namespace |

### InfoNodeResult

`(node_name: str, error_code: int, response: str)` -- one result per cluster node.

---

## Error Handling

All exceptions import from `aerospike_py` directly (not `aerospike_py.exception.X`) and are identical for sync/async clients. Catch specifics before `AerospikeError` (catch-all). Key library-specific behaviors:

- **`client.connect()` raises `ClusterError`** if no seed is reachable; the client auto-reconnects to surviving nodes after connect.
- **Single-record reads raise** `RecordNotFound` (missing), `RecordGenerationError` (CAS conflict, `POLICY_GEN_EQ`), `RecordExistsError` (`CREATE_ONLY`), `AerospikeTimeoutError`.
- **Batch ops do NOT raise** for per-record failures — check `br.result` (0 = OK) per record. `batch_read` missing keys are simply absent from the dict view; `batch_operate`/`batch_remove`/`batch_write` return `BatchWriteResult` — iterate `.batch_records`.

```python
keys = [("test", "demo", f"id-{i}") for i in range(100)]
lazy = client.batch_read(keys)
missing = {f"id-{i}" for i in range(100)} - set(lazy.keys())   # absent = not found

results = client.batch_operate(keys, [{"op": aerospike.OPERATOR_INCR, "bin": "views", "val": 1}])
for br in results.batch_records:
    if br.result == aerospike.AEROSPIKE_OK and br.record is not None:
        ...                                       # success
    elif br.result == aerospike.AEROSPIKE_ERR_RECORD_NOT_FOUND:
        ...                                       # missing: br.key
```

For `batch_write`, also inspect `br.in_doubt` before retrying (write may have applied — see write.md).

### Result Code Reference

| Code | Constant | Exception |
|------|----------|-----------|
| 0 | AEROSPIKE_OK | (success) |
| 2 | AEROSPIKE_ERR_RECORD_NOT_FOUND | RecordNotFound |
| 3 | AEROSPIKE_ERR_RECORD_GENERATION | RecordGenerationError |
| 5 | AEROSPIKE_ERR_RECORD_EXISTS | RecordExistsError |
| 6 | AEROSPIKE_ERR_BIN_EXISTS | BinExistsError |
| 9 | AEROSPIKE_ERR_TIMEOUT | AerospikeTimeoutError |
| 12 | AEROSPIKE_ERR_BIN_TYPE | BinTypeError |
| 13 | AEROSPIKE_ERR_RECORD_TOO_BIG | RecordTooBig |
| 17 | AEROSPIKE_ERR_BIN_NOT_FOUND | BinNotFound |
| 21 | AEROSPIKE_ERR_BIN_NAME | BinNameError |
| 27 | AEROSPIKE_ERR_FILTERED_OUT | FilteredOut |
| 200 | AEROSPIKE_ERR_INDEX_FOUND | IndexFoundError |
| 201 | AEROSPIKE_ERR_INDEX_NOT_FOUND | IndexNotFound |
| 210 | AEROSPIKE_ERR_QUERY_ABORTED | QueryAbortedError |

---

## Exception Hierarchy

All exceptions are importable both from `aerospike_py` directly (e.g. `from aerospike_py import RecordNotFound`) and from `aerospike_py.exception` (e.g. `from aerospike_py.exception import RecordNotFound`). `aerospike_py.exception.TimeoutError` and `aerospike_py.exception.IndexError` are deprecated aliases for `AerospikeTimeoutError` and `AerospikeIndexError` respectively and emit a DeprecationWarning when accessed.

```
AerospikeError
+-- ClientError
|   +-- BackpressureError
+-- ClusterError
+-- InvalidArgError
+-- AerospikeTimeoutError
|   (TimeoutError -- deprecated alias)
+-- RecordError
|   +-- RecordNotFound
|   +-- RecordExistsError
|   +-- RecordGenerationError
|   +-- RecordTooBig
|   +-- BinNameError
|   +-- BinExistsError
|   +-- BinNotFound
|   +-- BinTypeError
|   +-- FilteredOut
+-- ServerError
    +-- AerospikeIndexError
    |   (IndexError -- deprecated alias)
    |   +-- IndexNotFound
    |   +-- IndexFoundError
    +-- QueryError
    |   +-- QueryAbortedError
    +-- AdminError
    +-- UDFError
```
