# Policy Reference

All policy dicts are passed as the `policy=` parameter to client methods.

---

## ReadPolicy

Used by: `get()`, `select()`, `exists()`

```python
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 2,
 "filter_expression": expr, "replica": POLICY_REPLICA_MASTER, "read_mode_ap": POLICY_READ_MODE_AP_ONE}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 1000 | Total transaction timeout (ms) |
| max_retries | int | 2 | Max retry attempts |
| sleep_between_retries | int | 0 | Sleep between retries (ms) |
| filter_expression | Any | | Expression filter |
| replica | int | POLICY_REPLICA_SEQUENCE | Replica policy (`POLICY_REPLICA_*`) |
| read_mode_ap | int | POLICY_READ_MODE_AP_ONE | AP read mode (`POLICY_READ_MODE_AP_*`) |

---

## WritePolicy

Used by: `put()`, `remove()`, `touch()`, `append()`, `prepend()`, `increment()`, `remove_bin()`, `operate()`, `operate_ordered()`

```python
{"socket_timeout": 30000, "total_timeout": 1000, "max_retries": 0,
 "durable_delete": False, "key": POLICY_KEY_DIGEST, "exists": POLICY_EXISTS_IGNORE,
 "gen": POLICY_GEN_IGNORE, "commit_level": POLICY_COMMIT_LEVEL_ALL,
 "ttl": 0, "filter_expression": expr}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 1000 | Total transaction timeout (ms) |
| max_retries | int | 0 | Max retry attempts |
| durable_delete | bool | false | Durable delete (Enterprise) |
| key | int | POLICY_KEY_DIGEST | Key send policy (`POLICY_KEY_*`) |
| exists | int | POLICY_EXISTS_IGNORE | Record existence policy (`POLICY_EXISTS_*`) |
| gen | int | POLICY_GEN_IGNORE | Generation policy (`POLICY_GEN_*`) |
| commit_level | int | POLICY_COMMIT_LEVEL_ALL | Commit level (`POLICY_COMMIT_LEVEL_*`) |
| ttl | int | 0 | Record TTL in seconds |
| filter_expression | Any | | Expression filter |

---

## WriteMeta

Used by: `put()`, `remove()`, `touch()`, `operate()` as `meta=` parameter

```python
{"gen": 1, "ttl": 300}
```

| Key | Type | Description |
|-----|------|-------------|
| gen | int | Expected generation for CAS (`POLICY_GEN_EQ`) |
| ttl | int | Record TTL in seconds |

---

## BatchPolicy

Used by: `batch_read()`, `batch_operate()`, `batch_remove()`

```python
{"socket_timeout": 30000, "total_timeout": 1000,
 "max_retries": 2, "filter_expression": expr}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 1000 | Total transaction timeout (ms) |
| max_retries | int | 2 | Max retry attempts |
| filter_expression | Any | | Expression filter |

---

## QueryPolicy

Used by: `Query.results()`, `Query.foreach()`

```python
{"socket_timeout": 30000, "total_timeout": 0, "max_retries": 2,
 "max_records": 1000, "records_per_second": 0, "filter_expression": expr}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| socket_timeout | int | 30000 | Socket timeout (ms) |
| total_timeout | int | 0 | Total timeout (0 = no limit) |
| max_retries | int | 2 | Max retry attempts |
| max_records | int | 0 | Max records to return (0 = all) |
| records_per_second | int | 0 | Rate limit (0 = unlimited) |
| filter_expression | Any | | Expression filter |

---

## AdminPolicy

Used by: all `admin_*` methods, index operations, `truncate()`

```python
{"timeout": 5000}
```

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| timeout | int | 1000 | Admin operation timeout (ms) |

---

## Key Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `POLICY_EXISTS_IGNORE` | 0 | Upsert (default) |
| `POLICY_EXISTS_CREATE_ONLY` | 4 | Error if exists |
| `POLICY_EXISTS_UPDATE_ONLY` | 1 | Error if not exists |
| `POLICY_EXISTS_REPLACE` | 2 | Full replace (drops other bins) |
| `POLICY_GEN_IGNORE` | 0 | Ignore generation (default) |
| `POLICY_GEN_EQ` | 1 | Write only if gen matches |
| `POLICY_GEN_GT` | 2 | Write only if gen is greater |
| `POLICY_KEY_DIGEST` | 0 | Store digest only (default) |
| `POLICY_KEY_SEND` | 1 | Store original key on server |
| `TTL_NAMESPACE_DEFAULT` | 0 | Use namespace default |
| `TTL_NEVER_EXPIRE` | -1 | Never expire |
| `TTL_DONT_UPDATE` | -2 | Keep existing TTL |

Full constants reference: `./constants.md`
