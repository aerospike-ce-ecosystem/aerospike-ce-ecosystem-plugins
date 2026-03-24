---
name: aerospike-py-fastapi
description: "MUST USE for building FastAPI/REST API applications with Aerospike database. Contains production-ready patterns for aerospike-py (Rust/PyO3 async client) that CANNOT be inferred from general knowledge: correct AsyncClient lifespan management, FastAPI Depends injection for client, aerospike_py exception-to-HTTP-status mapping (RecordNotFound→404, RecordExistsError→409, BackpressureError→503), POLICY_EXISTS_CREATE_ONLY/UPDATE_ONLY for CRUD semantics, NamedTuple attribute access (record.bins not tuple unpacking), and global AerospikeError handler. Without this skill, generated code uses wrong import paths, missing DI patterns, and lacks backpressure/metrics/health checks. Triggers on: FastAPI + Aerospike, REST API + aerospike-py, CRUD API with Aerospike, web server/HTTP service backed by Aerospike NoSQL, uvicorn + Aerospike."
---

## 1. App Structure (Lifespan + DI)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends
from aerospike_py import AsyncClient
import aerospike_py

@asynccontextmanager
async def lifespan(app: FastAPI):
    client = AsyncClient({
        "hosts": [("127.0.0.1", 3000)],
        "max_concurrent_operations": 64,      # backpressure
        "operation_queue_timeout_ms": 5000,
    })
    aerospike_py.init_tracing()                # OpenTelemetry (optional)
    await client.connect()
    app.state.aerospike = client
    yield
    await client.close()
    aerospike_py.shutdown_tracing()

app = FastAPI(lifespan=lifespan)

def get_client(request: Request) -> AsyncClient:
    return request.app.state.aerospike
```

## 2. CRUD Endpoints

```python
from fastapi.responses import JSONResponse

NS, SET = "app", "records"

@app.post("/records/{pk}", status_code=201)
async def create(pk: str, body: dict, client: AsyncClient = Depends(get_client)):
    try:
        await client.put((NS, SET, pk), body,
                         policy={"exists": aerospike_py.POLICY_EXISTS_CREATE_ONLY})
        return {"key": pk}
    except aerospike_py.RecordExistsError:
        return JSONResponse(status_code=409, content={"error": "already exists"})

@app.get("/records/{pk}")
async def read(pk: str, client: AsyncClient = Depends(get_client)):
    try:
        record = await client.get((NS, SET, pk))
        return record.bins                     # NamedTuple attribute access
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "not found"})

@app.put("/records/{pk}")
async def update(pk: str, body: dict, client: AsyncClient = Depends(get_client)):
    try:
        await client.put((NS, SET, pk), body,
                         policy={"exists": aerospike_py.POLICY_EXISTS_UPDATE_ONLY})
        return {"key": pk}
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "not found"})

@app.delete("/records/{pk}", status_code=204)
async def delete(pk: str, client: AsyncClient = Depends(get_client)):
    try:
        await client.remove((NS, SET, pk))
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "not found"})
```

## 3. Global Error Handler

```python
@app.exception_handler(aerospike_py.BackpressureError)
async def backpressure_handler(request, exc):
    return JSONResponse(status_code=503, content={"error": "server busy, retry later"})

@app.exception_handler(aerospike_py.AerospikeError)
async def aerospike_error_handler(request, exc):
    return JSONResponse(status_code=500, content={"error": str(exc)})
```

## 4. Exception → HTTP Status Mapping

| Exception | HTTP Status | Meaning |
|-----------|-------------|---------|
| `RecordNotFound` | 404 | Record does not exist |
| `RecordExistsError` | 409 | Record already exists (CREATE_ONLY) |
| `RecordGenerationError` | 409 | Optimistic lock conflict |
| `BackpressureError` | 503 | Too many concurrent operations |
| `AerospikeTimeoutError` | 504 | Operation timed out |
| `AerospikeError` | 500 | Catch-all server error |

## 5. Health Check

```python
@app.get("/health")
async def health(client: AsyncClient = Depends(get_client)):
    try:
        nodes = client.get_node_names()   # sync call, NOT awaitable
        return {"status": "ok", "nodes": len(nodes)}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
```

## 6. Metrics Endpoint

```python
from fastapi import Response

@app.get("/metrics")
async def metrics():
    return Response(
        content=aerospike_py.get_metrics(),
        media_type="text/plain; version=0.0.4",
    )
```

Or use the built-in server: `aerospike_py.start_metrics_server(port=9464)` in lifespan.

## 7. Key Patterns

- **Lifespan**: Create `AsyncClient` in lifespan, store on `app.state`, close on shutdown
- **DI**: Use `Depends(get_client)` for every endpoint — never create client per-request
- **Exceptions on module**: `aerospike_py.RecordNotFound` (NOT `aerospike_py.exception.RecordNotFound`)
- **NamedTuple returns**: `record.bins`, `record.meta.gen` (NOT tuple unpacking)
- **get_node_names()**: Always sync, even on AsyncClient
- **Backpressure**: Set `max_concurrent_operations` to prevent connection pool exhaustion

Detail: `../aerospike-py-api/reference/client-config.md` | `../aerospike-py-api/reference/admin.md`
