"""Fast happy-path AerospikeCluster CR lifecycle (~1–2 min).

The lightweight cousin of the Ginkgo "Basic single-node cluster" Context.
Used as:
  - PR-time fast gate vs the 15-min Ginkgo run
  - Sanity check that the helm release reconciles a CR end-to-end

Reuses the session-scoped `live_cluster` fixture which already applied a
basic CR and waited for Completed — this test just asserts everything is
in shape, then a separate test verifies clean deletion.
"""

from __future__ import annotations

import json
import logging

import pytest

from helpers.cli import run, run_text
from helpers.waits import wait_asc_gone

logger = logging.getLogger(__name__)


@pytest.mark.smoke
def test_basic_cluster_phase_completed(live_cluster: dict) -> None:
    """Phase reaches Completed (already enforced by the fixture, but assert here for the report)."""
    name, ns = live_cluster["name"], live_cluster["namespace"]
    phase = run_text(["kubectl", "get", "asc", name, "-n", ns, "-o", "jsonpath={.status.phase}"])
    assert phase == "Completed", f"asc/{name} phase={phase!r}, want Completed"


@pytest.mark.smoke
def test_basic_cluster_resources_exist(live_cluster: dict) -> None:
    """StatefulSet, headless Service, ConfigMap, PDB all present for the CR."""
    name, ns = live_cluster["name"], live_cluster["namespace"]

    # StatefulSet — name pattern is <cluster>-<rackID>
    out = run_text(["kubectl", "get", "statefulset", "-n", ns, "-o", "jsonpath={.items[*].metadata.name}"])
    sts = [s for s in out.split() if s.startswith(f"{name}-")]
    assert sts, f"no StatefulSet for cluster {name} (got: {out!r})"

    # Headless Service named exactly the cluster name
    svc = run(["kubectl", "get", "svc", name, "-n", ns], check=False, quiet=True)
    assert svc.returncode == 0, f"headless Service {name} missing in ns/{ns}"

    # ConfigMap matching the cluster (name-prefixed)
    out = run_text(["kubectl", "get", "cm", "-n", ns, "-o", "jsonpath={.items[*].metadata.name}"])
    cms = [c for c in out.split() if c.startswith(f"{name}-")]
    assert cms, f"no ConfigMap with prefix {name}- in ns/{ns}"

    # PodDisruptionBudget — chart creates one per cluster by default
    out = run_text(["kubectl", "get", "pdb", "-n", ns, "-o", "jsonpath={.items[*].metadata.name}"])
    pdbs = [p for p in out.split() if p.startswith(name)]
    assert pdbs, f"no PodDisruptionBudget for cluster {name} in ns/{ns}"


@pytest.mark.smoke
def test_basic_cluster_status_size_matches_spec(live_cluster: dict) -> None:
    name, ns = live_cluster["name"], live_cluster["namespace"]
    cr = json.loads(run_text(["kubectl", "get", "asc", name, "-n", ns, "-o", "json"]))
    spec_size = cr["spec"]["size"]
    status_size = cr.get("status", {}).get("size")
    assert status_size == spec_size, f"status.size={status_size!r} should equal spec.size={spec_size!r}"

    pods = cr.get("status", {}).get("pods", {}) or {}
    ready = sum(1 for p in pods.values() if p.get("isRunningAndReady"))
    assert ready == spec_size, f"{ready} pods running+ready, expected {spec_size}"


@pytest.mark.smoke
def test_basic_cluster_deletion_clean(live_cluster: dict) -> None:
    """Delete the CR explicitly and verify the namespace returns to empty.

    Important: this runs LAST because it tears down the live_cluster fixture
    out from under any later test. pytest's per-file ordering plus the
    `live_cluster` being session-scoped means subsequent api tests will
    re-trigger the fixture's teardown→re-setup if needed.

    To avoid that, we re-apply the CR at the end so subsequent tests can
    still use the live cluster. This is wasteful (one extra ~30s wait) but
    keeps the smoke lane self-contained.
    """
    from helpers import env
    from helpers.waits import wait_asc_completed

    name, ns = live_cluster["name"], live_cluster["namespace"]

    run(["kubectl", "delete", "asc", name, "-n", ns, "--wait=true", "--timeout=2m"])
    wait_asc_gone(name, ns, timeout=120)

    out = run_text(["kubectl", "get", "asc", "-n", ns, "-o", "jsonpath={.items[*].metadata.name}"])
    assert not out.strip(), f"asc CRs remain after delete: {out!r}"

    # Re-create so downstream session-scoped tests still find a Completed cluster.
    import yaml as _yaml

    sample = env.OPERATOR_REPO / "config" / "samples" / "acko_v1alpha1_aerospikecluster.yaml"
    doc = _yaml.safe_load(sample.read_text())
    doc["metadata"]["name"] = name
    doc["metadata"]["namespace"] = ns
    text = _yaml.safe_dump(doc, sort_keys=False)
    import subprocess

    subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=text,
        text=True,
        capture_output=True,
        check=True,
    )
    wait_asc_completed(name, ns, timeout=300)
