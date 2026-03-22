"""
Minimal FastAPI + Aerospike CRUD API.

Run:
    pip install fastapi uvicorn aerospike-py
    uvicorn minimal-app:app --reload

API docs: http://localhost:8000/docs

Environment variables:
    AEROSPIKE_HOST  -- Aerospike host (default: 127.0.0.1)
    AEROSPIKE_PORT  -- Aerospike port (default: 3000)
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse

import aerospike_py
from aerospike_py import AsyncClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AEROSPIKE_HOST = os.getenv("AEROSPIKE_HOST", "127.0.0.1")
AEROSPIKE_PORT = int(os.getenv("AEROSPIKE_PORT", "3000"))
NAMESPACE = "test"
SET_NAME = "demo"


# ---------------------------------------------------------------------------
# Lifespan: manage AsyncClient lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Aerospike on startup, close on shutdown."""
    aerospike_py.set_log_level(aerospike_py.LOG_LEVEL_INFO)

    client = AsyncClient({"hosts": [(AEROSPIKE_HOST, AEROSPIKE_PORT)]})
    await client.connect()
    app.state.aerospike = client

    yield

    await client.close()


app = FastAPI(
    title="Aerospike CRUD API",
    description="Minimal FastAPI app backed by Aerospike NoSQL via aerospike-py",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Dependency: get AsyncClient from app state
# ---------------------------------------------------------------------------


def get_client(request: Request) -> AsyncClient:
    """Retrieve the shared AsyncClient instance."""
    return request.app.state.aerospike


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
async def health(client: AsyncClient = Depends(get_client)):
    """Check Aerospike connectivity."""
    connected = client.is_connected()
    return {"status": "ok" if connected else "degraded", "aerospike": connected}


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@app.put("/records/{pk}")
async def put_record(
    pk: str,
    bins: dict[str, Any],
    ttl: int | None = None,
    client: AsyncClient = Depends(get_client),
):
    """Create or update a record."""
    meta = {"ttl": ttl} if ttl is not None else None
    await client.put((NAMESPACE, SET_NAME, pk), bins, meta=meta)
    return {"status": "ok", "key": pk}


@app.get("/records/{pk}")
async def get_record(pk: str, client: AsyncClient = Depends(get_client)):
    """Read a record by primary key."""
    try:
        record = await client.get((NAMESPACE, SET_NAME, pk))
        return {
            "key": pk,
            "bins": record.bins,
            "generation": record.meta.gen,
            "ttl": record.meta.ttl,
        }
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})


@app.delete("/records/{pk}")
async def delete_record(pk: str, client: AsyncClient = Depends(get_client)):
    """Delete a record by primary key."""
    try:
        await client.remove((NAMESPACE, SET_NAME, pk))
        return {"status": "deleted", "key": pk}
    except aerospike_py.RecordNotFound:
        return JSONResponse(status_code=404, content={"error": "Record not found"})


# ---------------------------------------------------------------------------
# Prometheus metrics (optional)
# ---------------------------------------------------------------------------


@app.get("/metrics")
async def metrics():
    """Expose Aerospike client metrics in Prometheus text format."""
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=aerospike_py.get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
