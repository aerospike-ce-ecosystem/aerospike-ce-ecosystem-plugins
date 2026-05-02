"""Tiny httpx wrapper for the cluster-manager UI api.

This is the assertion-heavy piece where Python pulls its weight: structured
responses, automatic JSON, and rich pytest failure introspection — vs
`curl ... | jq` strings in bash.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ApiClient:
    """Synchronous httpx client pinned to the api base URL.

    Synchronous because pytest-asyncio's `auto` mode adds friction for tests
    that don't actually need concurrency, and our smokes are sequential by
    nature (POST then DELETE then re-GET).
    """

    def __init__(self, base_url: str, *, timeout: float = 10.0):
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self.base_url = base_url
        self._openapi_cache: dict | None = None

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -----------------------------------------------------------------
    # Generic verbs — return Response so the caller asserts on it.
    # -----------------------------------------------------------------
    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._client.get(path, **kwargs)

    def post(self, path: str, json: Any | None = None, **kwargs) -> httpx.Response:
        return self._client.post(path, json=json, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self._client.delete(path, **kwargs)

    # -----------------------------------------------------------------
    # /api/openapi.json convenience — used to validate that the spec
    # matches what we're testing, and to discover routes. Cached because
    # the spec is static for the lifetime of the api process and tests
    # often probe several paths in a row.
    # -----------------------------------------------------------------
    def openapi(self) -> dict:
        cached = self._openapi_cache
        if cached is None:
            r = self.get("/api/openapi.json")
            r.raise_for_status()
            cached = r.json()
            self._openapi_cache = cached
        return cached

    def has_path(self, path: str) -> bool:
        return path in self.openapi().get("paths", {})

    def k8s_management_enabled(self) -> bool:
        return any(p.startswith("/api/v1/k8s/") for p in self.openapi().get("paths", {}))
