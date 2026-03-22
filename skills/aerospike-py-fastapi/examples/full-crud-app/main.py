"""
FastAPI application with Aerospike NoSQL backend.

Structured project layout with routers, configuration, dependency injection,
and observability (Prometheus metrics + OpenTelemetry tracing).

Run:
    uvicorn main:app --reload
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

import aerospike_py
from aerospike_py import AsyncClient

from config import settings
from routers import records


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage AsyncClient lifecycle and observability."""
    # Logging
    aerospike_py.set_log_level(settings.log_level)

    # Tracing (reads OTEL_EXPORTER_OTLP_ENDPOINT env var)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", settings.otel_endpoint)
    os.environ.setdefault("OTEL_SERVICE_NAME", settings.otel_service_name)
    aerospike_py.init_tracing()

    # Aerospike client
    client = AsyncClient(
        {
            "hosts": [(settings.aerospike_host, settings.aerospike_port)],
            "max_concurrent_operations": settings.max_concurrent_operations,
            "max_conns_per_node": 300,
            "min_conns_per_node": 10,
        }
    )
    await client.connect()
    app.state.aerospike = client

    yield

    await client.close()
    aerospike_py.shutdown_tracing()


app = FastAPI(
    title="Aerospike FastAPI CRUD",
    description="Full-featured CRUD API backed by Aerospike via aerospike-py",
    version="0.1.0",
    lifespan=lifespan,
)

# Register routers
app.include_router(records.router)


# ---------------------------------------------------------------------------
# Global endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Liveness check."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    """Expose Aerospike client metrics in Prometheus text format."""
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        content=aerospike_py.get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
