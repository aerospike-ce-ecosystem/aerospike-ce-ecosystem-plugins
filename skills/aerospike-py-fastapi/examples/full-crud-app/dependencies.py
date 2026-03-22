"""FastAPI dependency injection for aerospike-py AsyncClient."""

from __future__ import annotations

from fastapi import Request

from aerospike_py import AsyncClient


def get_client(request: Request) -> AsyncClient:
    """Retrieve the shared AsyncClient from application state."""
    return request.app.state.aerospike
