"""UI api CRUD smokes A–G.

Re-asserts the four 500-error fixes from cluster-manager #257-#260 against
a real binary every release, plus connection lifecycle, cluster reachability,
indexes idempotency, and X-Request-ID round-trip.

Tests are ordered (A creates the connection that B–F depend on, A2 closes
it). pytest's intra-file order matches definition order, so this works
without explicit pytest-ordering.
"""

from __future__ import annotations

import logging

import pytest

from helpers.api_client import ApiClient

logger = logging.getLogger(__name__)


# Module-level cache so test functions can share a connection id without
# the awkwardness of class-scoped fixtures.
_state: dict[str, str] = {}


def _seed_host(live_cluster: dict) -> str:
    return f"{live_cluster['name']}.{live_cluster['namespace']}.svc.cluster.local"


# ---------------------------------------------------------------------------
# A. Connection lifecycle: create → list → (close in A2 at the end)
# ---------------------------------------------------------------------------
@pytest.mark.smoke
def test_a_create_connection(api: ApiClient, live_cluster: dict) -> None:
    seed = _seed_host(live_cluster)
    r = api.post("/api/v1/connections", json={"name": "smoke", "hosts": [seed], "port": 3000})
    assert r.status_code == 201, f"POST /api/v1/connections want 201, got {r.status_code}: {r.text}"

    body = r.json()
    assert body["id"], "response missing id"
    assert "createdAt" in body
    _state["conn_id"] = body["id"]

    listing = api.get("/api/v1/connections")
    assert listing.status_code == 200
    ids = [c["id"] for c in listing.json()]
    assert body["id"] in ids, f"newly-created id not in list: {ids}"


# ---------------------------------------------------------------------------
# B. Cluster reachability — proves aerospike-py wiring
# ---------------------------------------------------------------------------
@pytest.mark.smoke
def test_b_cluster_reachability(api: ApiClient) -> None:
    conn_id = _state["conn_id"]
    r = api.get(f"/api/v1/clusters/{conn_id}")
    assert r.status_code == 200
    body = r.json()
    ns_names = [n["name"] for n in body.get("namespaces", [])]
    assert "test" in ns_names, f"expected 'test' namespace, got {ns_names}"


# ---------------------------------------------------------------------------
# C. sample-data partial-success contract (#257)
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.regression_guard
def test_c_sample_data_returns_201_with_counts(api: ApiClient) -> None:
    conn_id = _state["conn_id"]
    r = api.post(
        f"/api/v1/sample-data/{conn_id}",
        json={"namespace": "test", "setName": "smoke30", "recordCount": 10},
    )
    assert r.status_code == 201, f"sample-data must always be 201; got {r.status_code}: {r.text}"
    body = r.json()
    for key in ("recordsCreated", "recordsFailed", "indexesCreated", "indexesFailed"):
        assert key in body, f"sample-data response missing '{key}': {body.keys()}"


@pytest.mark.smoke
@pytest.mark.regression_guard
def test_c_sample_data_bad_namespace_still_201(api: ApiClient) -> None:
    """Bad namespace must NOT 500 — partial-success contract (#257)."""
    conn_id = _state["conn_id"]
    r = api.post(
        f"/api/v1/sample-data/{conn_id}",
        json={"namespace": "this-ns-does-not-exist-XYZ", "setName": "smoke", "recordCount": 1},
    )
    assert r.status_code == 201, f"bad-ns must be 201 partial-success, NEVER 500; got {r.status_code}"
    assert r.json().get("recordsFailed", 0) >= 1


# ---------------------------------------------------------------------------
# D. records empty/sparse namespace (#259)
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.regression_guard
def test_d_records_empty_set_returns_200(api: ApiClient) -> None:
    conn_id = _state["conn_id"]
    r = api.get(
        f"/api/v1/records/{conn_id}",
        params={
            "ns": "test",
            "set": "does-not-exist",
            "pageSize": 3,
        },
    )
    assert r.status_code == 200, f"empty set must be 200, got {r.status_code}: {r.text}"
    assert r.json()["records"] == [], f"records should be []: {r.json()}"


# ---------------------------------------------------------------------------
# E. query pkType=auto (#258)
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.regression_guard
def test_e_query_pktype_auto(api: ApiClient) -> None:
    conn_id = _state["conn_id"]
    r = api.post(
        f"/api/v1/query/{conn_id}",
        json={"namespace": "test", "maxRecords": 3, "pkType": "auto"},
    )
    assert r.status_code == 200, f"query pkType=auto must be 200, got {r.status_code}: {r.text}"
    assert isinstance(r.json().get("records"), list)


# ---------------------------------------------------------------------------
# F. indexes idempotency (#260)
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.regression_guard
def test_f_indexes_create_delete_idempotent(api: ApiClient) -> None:
    conn_id = _state["conn_id"]
    payload = {
        "namespace": "test",
        "set": "smoke30",
        "name": "idx_smoke30_int",
        "bin": "bin_int",
        "type": "numeric",
    }
    r = api.post(f"/api/v1/indexes/{conn_id}", json=payload)
    assert r.status_code == 201, f"create idx → 201; got {r.status_code}: {r.text}"
    assert r.json().get("state") in ("building", "ready")

    r = api.delete(f"/api/v1/indexes/{conn_id}", params={"name": "idx_smoke30_int", "ns": "test"})
    assert r.status_code == 204, f"first DELETE → 204; got {r.status_code}: {r.text}"

    # Idempotent — calling DELETE on an already-deleted name must NOT 500.
    r = api.delete(f"/api/v1/indexes/{conn_id}", params={"name": "idx_smoke30_int", "ns": "test"})
    assert r.status_code == 204, f"idempotent DELETE → 204; got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# G. X-Request-ID round-trip
# ---------------------------------------------------------------------------
@pytest.mark.smoke
def test_g_x_request_id_echoed(api: ApiClient) -> None:
    rid = "probe-pytest-x-request-id"
    r = api.get("/api/v1/connections", headers={"X-Request-ID": rid})
    assert r.headers.get("x-request-id") == rid, (
        f"x-request-id must echo back unchanged; got {r.headers.get('x-request-id')!r}"
    )


# ---------------------------------------------------------------------------
# A2. Close out the connection (depends on A having run)
# ---------------------------------------------------------------------------
@pytest.mark.smoke
def test_z_delete_connection(api: ApiClient) -> None:
    conn_id = _state.pop("conn_id", None)
    if not conn_id:
        pytest.skip("test_a_create_connection didn't run / produce an id")
    r = api.delete(f"/api/v1/connections/{conn_id}")
    assert r.status_code == 204

    r = api.get(f"/api/v1/connections/{conn_id}")
    assert r.status_code == 404
