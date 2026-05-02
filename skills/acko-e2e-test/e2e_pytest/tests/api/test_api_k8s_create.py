"""api-mediated AerospikeCluster CRUD via /api/v1/k8s/clusters/...

Real UI users create AerospikeCluster CRs through the api, not directly
with `kubectl`. The whole `/api/v1/k8s/clusters/...` family was previously
untested in e2e until this lane.
"""

from __future__ import annotations

import logging

import pytest
import yaml

from helpers.api_client import ApiClient
from helpers.cli import run, run_text
from helpers.waits import wait_asc_completed, wait_asc_gone, wait_for

logger = logging.getLogger(__name__)


@pytest.fixture
def k8s_test_cluster_name() -> str:
    return "api-smoke"


@pytest.mark.smoke
def test_k8s_management_routes_exposed(api: ApiClient) -> None:
    """The `/api/v1/k8s/*` family must be present in openapi (K8S_MANAGEMENT_ENABLED)."""
    paths = api.openapi().get("paths", {})
    k8s_paths = [p for p in paths if p.startswith("/api/v1/k8s/")]
    assert len(k8s_paths) >= 5, (
        f"expected ≥5 /api/v1/k8s/* routes (K8S_MANAGEMENT_ENABLED), got {len(k8s_paths)}: {k8s_paths}"
    )


@pytest.mark.smoke
def test_create_cluster_via_api(
    api: ApiClient,
    helm_release: dict,
    k8s_test_cluster_name: str,
) -> None:
    """End-to-end: api POST → CR appears → Completed → GET → health → yaml → DELETE → 404."""
    name = k8s_test_cluster_name
    ns = "aerospike-api-test"

    # Make sure the target namespace exists
    yaml_text = run_text(
        [
            "kubectl",
            "create",
            "namespace",
            ns,
            "--dry-run=client",
            "-o",
            "yaml",
        ]
    )
    run(["kubectl", "apply", "-f", "-"], stdin=yaml_text)

    # ---- 1. POST: create CR through the api ----
    payload = {
        "namespace": ns,
        "name": name,
        "size": 1,
        "image": "aerospike:ce-8.1.1.1",
        "aerospikeConfig": {
            "service": {"cluster-name": name, "proto-fd-max": 15000},
            "network": {
                "service": {"address": "any", "port": 3000},
                "heartbeat": {"mode": "mesh", "port": 3002},
                "fabric": {"address": "any", "port": 3001},
            },
            "namespaces": [
                {
                    "name": "test",
                    "replication-factor": 1,
                    "storage-engine": {"type": "memory", "data-size": 1073741824},
                }
            ],
            "logging": [{"name": "console", "any": "info"}],
        },
    }
    r = api.post("/api/v1/k8s/clusters", json=payload)
    assert r.status_code in (200, 201, 202), (
        f"POST /api/v1/k8s/clusters expected 200/201/202; got {r.status_code}: {r.text}"
    )

    try:
        # ---- 2. CR appears + reaches Completed ----
        wait_for(
            lambda: run(["kubectl", "get", "asc", name, "-n", ns], check=False, quiet=True).returncode == 0,
            timeout=30,
            interval=1,
            description=f"asc/{name} appears in {ns}",
        )
        wait_asc_completed(name, ns, timeout=300)

        # ---- 3. GET single cluster ----
        r = api.get(f"/api/v1/k8s/clusters/{ns}/{name}")
        assert r.status_code == 200
        body = r.json()
        assert body.get("metadata", {}).get("name") == name

        # ---- 4. GET .../health ----
        r = api.get(f"/api/v1/k8s/clusters/{ns}/{name}/health")
        assert r.status_code == 200

        # ---- 5. GET .../yaml — body must be parseable YAML ----
        r = api.get(f"/api/v1/k8s/clusters/{ns}/{name}/yaml")
        assert r.status_code == 200
        # raises if it isn't valid YAML
        parsed = yaml.safe_load(r.text)
        assert parsed is not None, f"yaml endpoint returned empty/None: {r.text!r}"

        # ---- 6. DELETE ----
        r = api.delete(f"/api/v1/k8s/clusters/{ns}/{name}")
        assert r.status_code in (200, 202, 204), f"DELETE expected 200/202/204; got {r.status_code}: {r.text}"

        wait_asc_gone(name, ns, timeout=120)

        r = api.get(f"/api/v1/k8s/clusters/{ns}/{name}")
        assert r.status_code == 404, f"GET after DELETE expected 404; got {r.status_code}: {r.text}"

    finally:
        # Best-effort cleanup
        run(["kubectl", "delete", "asc", name, "-n", ns, "--ignore-not-found"], check=False)
        run(["kubectl", "delete", "ns", ns, "--ignore-not-found", "--wait=false"], check=False)
