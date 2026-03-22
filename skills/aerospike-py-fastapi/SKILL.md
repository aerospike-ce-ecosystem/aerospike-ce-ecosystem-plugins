---
name: aerospike-py-fastapi
description: "MUST USE for building FastAPI/REST API applications with Aerospike database. Contains production-ready patterns for aerospike-py (Rust/PyO3 async client) that CANNOT be inferred from general knowledge: correct AsyncClient lifespan management, FastAPI Depends injection for client, aerospike_py exception-to-HTTP-status mapping (RecordNotFound→404, RecordExistsError→409, BackpressureError→503), POLICY_EXISTS_CREATE_ONLY/UPDATE_ONLY for CRUD semantics, NamedTuple attribute access (record.bins not tuple unpacking), and global AerospikeError handler. Without this skill, generated code uses wrong import paths, missing DI patterns, and lacks backpressure/metrics/health checks. Triggers on: FastAPI + Aerospike, REST API + aerospike-py, CRUD API with Aerospike, web server/HTTP service backed by Aerospike NoSQL, uvicorn + Aerospike."
---

# FastAPI + aerospike-py: Complete Guide

Build production-ready FastAPI applications backed by Aerospike NoSQL using the async `aerospike-py` client.

## CRITICAL: aerospike-py Import Patterns

All exceptions and constants live directly on the `aerospike_py` module — there is NO `aerospike_py.exception` submodule for catching errors. The library is a Rust/PyO3 extension where exceptions are registered at the top level.

```python
# CORRECT imports
import aerospike_py
from aerospike_py import AsyncClient

# Catch exceptions from the top-level module
except aerospike_py.RecordNotFound:       # 404
except aerospike_py.RecordExistsError:    # 409 (duplicate)
except aerospike_py.RecordGenerationError: # 409 (optimistic lock)
except aerospike_py.BackpressureError:    # 503 (overloaded)
except aerospike_py.AerospikeTimeoutError: # 504
except aerospike_py.AerospikeError:       # catch-all base class

# WRONG - these do NOT work:
# from aerospike_py.exception import RecordNotFound  ← NO
# from aerospike_py.errors import RecordNotFound     ← NO
```

All return types are **NamedTuples** — use attribute access, not tuple unpacking:

```python
record = await client.get(key)
record.bins          # dict[str, Any] — the bin data
record.meta.gen      # int — generation number
record.meta.ttl      # int — TTL in seconds
record.key.user_key  # the original primary key

# AVOID tuple unpacking (fragile, less readable):
# _, meta, bins = await client.get(key)  ← don't do this
```

Key write policies for CRUD semantics (these are essential for correct HTTP status codes):

| Operation | Policy | Effect |
|-----------|--------|--------|
| Create (POST) | `{"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY}` | Raises `RecordExistsError` if duplicate → 409 |
| Update (PUT) | `{"exists": aerospike_py.POLICY_EXISTS_UPDATE_ONLY}` | Raises `RecordNotFound` if missing → 404 |
| Upsert (PUT) | `{"exists": aerospike_py.POLICY_EXISTS_IGNORE}` | Default — create or overwrite |

## 1. Quick Start: Minimal FastAPI + Aerospike

Install and run in 60 seconds:

```bash
pip install fastapi uvicorn aerospike-py
# or
uv add fastapi uvicorn aerospike-py
```

Complete single-file app (`app.py`):

```python
"""Minimal FastAPI + Aerospike CRUD API."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse

import aerospike_py
from aerospike_py import AsyncClient

NAMESPACE = "test"
SET_NAME = "demo"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect AsyncClient on startup, close on shutdown."""
    client = AsyncClient({
        "hosts": [(os.getenv("AEROSPIKE_HOST", "127.0.0.1"),
                   int(os.getenv("AEROSPIKE_PORT", "3000")))],
    })
    await client.connect()
    app.state.aerospike = client
    yield
    await client.close()


app = FastAPI(title="Aerospike CRUD API", lifespan=lifespan)


def get_client(request: Request) -> AsyncClient:
    return request.app.state.aerospike


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.put("/records/{pk}")
async def put_record(pk: str, bins: dict, client: AsyncClient = Depends(get_client)):
    await client.put((NAMESPACE, SET_NAME, pk), bins)
    return {"status": "ok", "key": pk}


@app.get("/records/{pk}")
async def get_record(pk: str, client: AsyncClient = Depends(get_client)):
    try:
        record = await client.get((NAMESPACE, SET_NAME, pk))
        return {"key": pk, "bins": record.bins, "generation": record.meta.gen}
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})


@app.delete("/records/{pk}")
async def delete_record(pk: str, client: AsyncClient = Depends(get_client)):
    try:
        await client.remove((NAMESPACE, SET_NAME, pk))
        return {"status": "deleted", "key": pk}
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})
```

Run it:

```bash
uvicorn app:app --reload
# API docs at http://localhost:8000/docs
```

## 2. Project Setup

### pyproject.toml

```toml
[project]
name = "my-aerospike-api"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "aerospike-py>=0.5",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = ["pytest", "httpx", "pytest-asyncio"]
```

### uv commands

```bash
uv init my-aerospike-api
cd my-aerospike-api
uv add fastapi "uvicorn[standard]" aerospike-py pydantic pydantic-settings
uv add --dev pytest httpx pytest-asyncio
```

## 3. Core Patterns

### AsyncClient Lifespan Management

The correct pattern uses FastAPI's lifespan context manager. The AsyncClient must be created and connected during startup, and closed during shutdown.

```python
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
import aerospike_py
from aerospike_py import AsyncClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -- Startup --
    aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_INFO)

    client = AsyncClient({
        "hosts": [(os.getenv("AEROSPIKE_HOST", "127.0.0.1"),
                   int(os.getenv("AEROSPIKE_PORT", "3000")))],
        "max_concurrent_operations": 64,  # backpressure for high concurrency
    })
    await client.connect()
    app.state.aerospike = client

    yield

    # -- Shutdown --
    await client.close()


app = FastAPI(lifespan=lifespan)
```

### Dependency Injection (use Depends, not private helpers)

Retrieve the AsyncClient from `app.state` via FastAPI's `Depends` — this is the canonical FastAPI pattern for dependency injection. Do not use private helper functions called manually inside each endpoint.

```python
from fastapi import Request, Depends
from aerospike_py import AsyncClient


def get_client(request: Request) -> AsyncClient:
    """Shared dependency to retrieve the AsyncClient from app state."""
    return request.app.state.aerospike
```

Use in every endpoint via `Depends`:

```python
@app.get("/records/{pk}")
async def get_record(pk: str, client: AsyncClient = Depends(get_client)):
    record = await client.get(("test", "demo", pk))
    return record.bins  # NamedTuple attribute, not tuple unpacking
```

### Error Handling Mapping

Map Aerospike exceptions to HTTP status codes:

```python
from fastapi import HTTPException
from fastapi.responses import JSONResponse
import aerospike_py


def aerospike_exception_handler(request, exc):
    """Global exception handler for Aerospike errors."""
    if isinstance(exc, aerospike_py.RecordNotFound):
        return JSONResponse(status_code=404, content={"error": "Record not found"})
    if isinstance(exc, aerospike_py.RecordExistsError):
        return JSONResponse(status_code=409, content={"error": "Record already exists"})
    if isinstance(exc, aerospike_py.RecordGenerationError):
        return JSONResponse(status_code=409, content={"error": "Conflict: record was modified"})
    if isinstance(exc, aerospike_py.FilteredOut):
        return JSONResponse(status_code=404, content={"error": "Record filtered out"})
    if isinstance(exc, aerospike_py.AerospikeTimeoutError):
        return JSONResponse(status_code=504, content={"error": "Database timeout"})
    if isinstance(exc, aerospike_py.AerospikeError):
        return JSONResponse(status_code=503, content={"error": f"Database error: {exc}"})
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


# Register the handler
app.add_exception_handler(aerospike_py.AerospikeError, aerospike_exception_handler)
```

Or handle per-endpoint:

```python
@app.get("/records/{pk}")
async def get_record(pk: str, client: AsyncClient = Depends(get_client)):
    try:
        record = await client.get(("test", "demo", pk))
        return {"bins": record.bins, "generation": record.meta.gen}
    except aerospike_py.RecordNotFound:
        raise HTTPException(status_code=404, detail="Record not found")
```

### Pydantic Models for Request/Response

```python
from typing import Any
from pydantic import BaseModel, Field


class RecordCreate(BaseModel):
    bins: dict[str, Any]
    ttl: int | None = Field(None, description="TTL in seconds")


class RecordResponse(BaseModel):
    key: str
    bins: dict[str, Any]
    generation: int
    ttl: int


class ErrorResponse(BaseModel):
    error: str
```

## 4. CRUD Endpoints

### PUT /records/{pk} -- Create or Update

```python
@app.put("/records/{pk}")
async def put_record(
    pk: str,
    body: RecordCreate,
    create_only: bool = False,
    client: AsyncClient = Depends(get_client),
):
    """Write a record. Set create_only=true to fail if the record already exists."""
    meta = {"ttl": body.ttl} if body.ttl is not None else None
    policy = None
    if create_only:
        policy = {"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY}

    try:
        await client.put(("test", "demo", pk), body.bins, meta=meta, policy=policy)
        return {"status": "ok", "key": pk}
    except aerospike_py.RecordExistsError:
        return JSONResponse(status_code=409, content={"error": "Record already exists"})
```

### GET /records/{pk} -- Read

```python
@app.get("/records/{pk}")
async def get_record(
    pk: str,
    bins: str | None = None,
    client: AsyncClient = Depends(get_client),
):
    """Read a record. Optionally select specific bins with ?bins=name,age."""
    try:
        key = ("test", "demo", pk)
        if bins:
            bin_list = [b.strip() for b in bins.split(",")]
            record = await client.select(key, bin_list)
        else:
            record = await client.get(key)
        return {
            "key": pk,
            "bins": record.bins,
            "generation": record.meta.gen,
            "ttl": record.meta.ttl,
        }
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})
```

### DELETE /records/{pk} -- Delete

```python
@app.delete("/records/{pk}")
async def delete_record(
    pk: str,
    generation: int | None = None,
    client: AsyncClient = Depends(get_client),
):
    """Delete a record. Optionally pass generation for optimistic locking."""
    try:
        meta = {"gen": generation} if generation is not None else None
        policy = {"gen": aerospike_py.POLICY_GEN_EQ} if generation is not None else None
        await client.remove(("test", "demo", pk), meta=meta, policy=policy)
        return {"status": "deleted", "key": pk}
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})
    except aerospike_py.RecordGenerationError:
        return JSONResponse(status_code=409, content={"error": "Generation mismatch"})
```

### GET /records -- Query with Expression Filters

```python
from aerospike_py import exp, predicates


@app.get("/records")
async def query_records(
    min_age: int | None = None,
    max_age: int | None = None,
    status: str | None = None,
    limit: int = 100,
    client: AsyncClient = Depends(get_client),
):
    """Query records with optional expression filters."""
    filters = []
    if min_age is not None:
        filters.append(exp.ge(exp.int_bin("age"), exp.int_val(min_age)))
    if max_age is not None:
        filters.append(exp.le(exp.int_bin("age"), exp.int_val(max_age)))
    if status is not None:
        filters.append(exp.eq(exp.string_bin("status"), exp.string_val(status)))

    query = client.query("test", "demo")
    policy = {"max_records": limit}
    if filters:
        expr = exp.and_(*filters) if len(filters) > 1 else filters[0]
        policy["filter_expression"] = expr

    records = await query.results(policy=policy)
    return [
        {"bins": r.bins, "generation": r.meta.gen}
        for r in records
        if r.bins is not None
    ]
```

## 5. Advanced Patterns

### Batch Operations

```python
from pydantic import BaseModel


class BatchReadRequest(BaseModel):
    keys: list[str]
    bins: list[str] | None = None


@app.post("/batch/read")
async def batch_read(body: BatchReadRequest, client: AsyncClient = Depends(get_client)):
    """Read multiple records in a single network call."""
    keys = [("test", "demo", pk) for pk in body.keys]
    result = await client.batch_read(keys, bins=body.bins)

    records = []
    for br in result.batch_records:
        if br.result == 0 and br.record is not None:
            _, meta, bins = br.record
            records.append({"bins": bins, "generation": meta.gen})
        else:
            records.append({"error": f"result_code={br.result}"})
    return records


class BatchOperateRequest(BaseModel):
    keys: list[str]
    increment_bin: str
    increment_value: int = 1


@app.post("/batch/increment")
async def batch_increment(body: BatchOperateRequest, client: AsyncClient = Depends(get_client)):
    """Increment a bin on multiple records atomically."""
    keys = [("test", "demo", pk) for pk in body.keys]
    ops = [{"op": aerospike_py.OPERATOR_INCR, "bin": body.increment_bin, "val": body.increment_value}]
    results = await client.batch_operate(keys, ops)
    return [{"bins": r.bins} for r in results]
```

### CDT Operations (List/Map)

```python
from aerospike_py import list_operations as lop, map_operations as mop


@app.post("/records/{pk}/list/{bin_name}/append")
async def list_append(
    pk: str, bin_name: str, value: Any, client: AsyncClient = Depends(get_client)
):
    """Append a value to a list bin."""
    ops = [
        lop.list_append(bin_name, value),
        lop.list_size(bin_name),
    ]
    record = await client.operate(("test", "demo", pk), ops)
    return {"bins": record.bins}


@app.post("/records/{pk}/map/{bin_name}/put")
async def map_put(
    pk: str, bin_name: str, key: str, value: Any,
    client: AsyncClient = Depends(get_client),
):
    """Put a key-value pair into a map bin."""
    ops = [
        mop.map_put(bin_name, key, value),
        mop.map_size(bin_name),
    ]
    record = await client.operate(("test", "demo", pk), ops)
    return {"bins": record.bins}
```

### Secondary Index + Query Endpoints

```python
@app.post("/indexes/{index_name}")
async def create_index(
    index_name: str,
    bin_name: str,
    index_type: str = "integer",
    client: AsyncClient = Depends(get_client),
):
    """Create a secondary index."""
    try:
        if index_type == "integer":
            await client.index_integer_create("test", "demo", bin_name, index_name)
        elif index_type == "string":
            await client.index_string_create("test", "demo", bin_name, index_name)
        return {"status": "created", "index": index_name}
    except aerospike_py.IndexFoundError:
        return JSONResponse(status_code=409, content={"error": "Index already exists"})


@app.delete("/indexes/{index_name}")
async def remove_index(index_name: str, client: AsyncClient = Depends(get_client)):
    """Remove a secondary index."""
    try:
        await client.index_remove("test", index_name)
        return {"status": "removed"}
    except aerospike_py.IndexNotFound:
        return JSONResponse(status_code=404, content={"error": "Index not found"})


@app.get("/query/range")
async def query_range(
    bin_name: str, min_val: int, max_val: int,
    client: AsyncClient = Depends(get_client),
):
    """Query records using a secondary index range predicate."""
    query = client.query("test", "demo")
    query.where(predicates.between(bin_name, min_val, max_val))
    records = await query.results()
    return [{"bins": r.bins} for r in records if r.bins is not None]
```

### Expression Filter Endpoints

```python
@app.get("/query/filter")
async def query_with_filter(
    active: bool | None = None,
    min_score: float | None = None,
    name_pattern: str | None = None,
    client: AsyncClient = Depends(get_client),
):
    """Query with server-side expression filters (no index required)."""
    filters = []
    if active is not None:
        filters.append(exp.eq(exp.bool_bin("active"), exp.bool_val(active)))
    if min_score is not None:
        filters.append(exp.ge(exp.float_bin("score"), exp.float_val(min_score)))
    if name_pattern is not None:
        filters.append(exp.regex_compare(name_pattern, 0, exp.string_bin("name")))

    query = client.query("test", "demo")
    policy = {}
    if filters:
        policy["filter_expression"] = exp.and_(*filters) if len(filters) > 1 else filters[0]

    records = await query.results(policy=policy)
    return [{"bins": r.bins} for r in records if r.bins is not None]
```

## 6. Observability

### Prometheus Metrics Endpoint

```python
from fastapi.responses import PlainTextResponse


@app.get("/metrics", response_class=PlainTextResponse)
async def prometheus_metrics():
    """Expose Aerospike client metrics in Prometheus text format."""
    return PlainTextResponse(
        content=aerospike_py.get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
```

### OpenTelemetry Tracing Setup

Add tracing to the lifespan:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Set environment variables before init_tracing()
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    os.environ.setdefault("OTEL_SERVICE_NAME", "my-fastapi-app")

    aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_INFO)
    aerospike_py.init_tracing()

    client = AsyncClient({
        "hosts": [(os.getenv("AEROSPIKE_HOST", "127.0.0.1"),
                   int(os.getenv("AEROSPIKE_PORT", "3000")))],
    })
    await client.connect()
    app.state.aerospike = client

    yield

    await client.close()
    aerospike_py.shutdown_tracing()
```

### Health Check Endpoint

```python
@app.get("/health")
async def health(client: AsyncClient = Depends(get_client)):
    """Health check that verifies Aerospike connectivity."""
    try:
        connected = client.is_connected()
        return {"status": "ok" if connected else "degraded", "aerospike": connected}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
```

## 7. Production Patterns

### Structured Project Layout

```
my-aerospike-api/
+-- app/
|   +-- __init__.py
|   +-- main.py              # FastAPI app, lifespan, router registration
|   +-- config.py            # Settings (pydantic-settings, env vars)
|   +-- dependencies.py      # get_client dependency
|   +-- models.py            # Pydantic request/response models
|   +-- routers/
|       +-- __init__.py
|       +-- records.py       # CRUD endpoints
|       +-- batch.py         # Batch operations
|       +-- query.py         # Query / filter endpoints
|       +-- observability.py # Metrics, health, tracing
+-- tests/
|   +-- conftest.py
|   +-- test_records.py
+-- pyproject.toml
```

### Backpressure Configuration

For high-concurrency production deployments, configure `max_concurrent_operations` to prevent overloading the Aerospike cluster:

```python
client = AsyncClient({
    "hosts": [("aerospike.prod", 3000)],
    "max_concurrent_operations": 64,       # limit in-flight ops
    "operation_queue_timeout_ms": 5000,    # fail after 5s in queue
    "max_conns_per_node": 300,
    "min_conns_per_node": 10,              # pre-warm connections
})
```

Handle backpressure errors:

```python
try:
    record = await client.get(key)
except aerospike_py.BackpressureError:
    return JSONResponse(status_code=503, content={"error": "Service overloaded, retry later"})
```

### Connection Pool Tuning

```python
client = AsyncClient({
    "hosts": [("aerospike.prod", 3000)],
    "max_conns_per_node": 300,        # match expected concurrent requests
    "min_conns_per_node": 10,         # avoid cold-start latency
    "conn_pools_per_node": 1,         # increase for >8 CPU cores
    "idle_timeout": 55000,            # below server proto-fd-idle-ms
    "timeout": 30000,                 # connection timeout
})
```

### Multiple Namespace Support

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aerospike_host: str = "127.0.0.1"
    aerospike_port: int = 3000
    aerospike_namespace: str = "test"
    aerospike_set: str = "demo"

    model_config = {"env_prefix": "APP_"}


settings = Settings()

# Use in endpoints
@app.put("/records/{pk}")
async def put_record(pk: str, bins: dict, client: AsyncClient = Depends(get_client)):
    await client.put((settings.aerospike_namespace, settings.aerospike_set, pk), bins)
    return {"status": "ok"}
```

## 8. Common Mistakes

### Wrong port

The default Aerospike port is **3000** for standard deployments. Development containers (like Podman-based dev environments) often use **18710**. Always check your configuration:

```python
# Standard deployment
config = {"hosts": [("127.0.0.1", 3000)]}

# Dev container / Podman
config = {"hosts": [("127.0.0.1", 18710)]}

# Best practice: use environment variables
config = {"hosts": [(os.getenv("AEROSPIKE_HOST", "127.0.0.1"),
                     int(os.getenv("AEROSPIKE_PORT", "3000")))]}
```

### Missing await on async operations

Every AsyncClient I/O method MUST be awaited:

```python
# WRONG -- returns a coroutine, does not execute
record = client.get(key)

# CORRECT
record = await client.get(key)
```

### Not closing client in lifespan

Always close the client on shutdown to flush pending operations and release connections:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncClient(config)
    await client.connect()
    app.state.aerospike = client
    yield
    await client.close()  # DO NOT FORGET THIS
```

### Forgetting cluster_name for Kubernetes deployments

When connecting to an Aerospike cluster deployed via the Kubernetes operator, you must set `cluster_name` to match the cluster's configured name:

```python
config = {
    "hosts": [("aerospike.default.svc.cluster.local", 3000)],
    "cluster_name": "aerospike",  # must match the K8s cluster name
}
```

### Using sync Client in async context

Never use the sync `aerospike_py.client()` in a FastAPI async handler. It blocks the event loop:

```python
# WRONG -- blocks the event loop
client = aerospike_py.client(config).connect()
record = client.get(key)  # blocks!

# CORRECT -- use AsyncClient
client = AsyncClient(config)
await client.connect()
record = await client.get(key)  # non-blocking
```

### Not handling RecordNotFound

Every `get()` call can raise `RecordNotFound`. Always handle it:

```python
try:
    record = await client.get(key)
    return record.bins
except aerospike_py.RecordNotFound:
    raise HTTPException(status_code=404, detail="Not found")
```

## Reference Examples

- Minimal single-file app: `./examples/minimal-app.py`
- Full structured CRUD app: `./examples/full-crud-app/`
