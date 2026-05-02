"""helm install + helm test + helm uninstall against a fresh namespace.

`helm template` (test_helm_matrix.py) catches manifest-level regressions but
misses things that only surface during apply: CRD ordering, hook race,
RBAC propagation, hanging helm-test pods (PR #236 type bug).

Uses a SEPARATE namespace + release name so it doesn't collide with the
session-wide install used by api/observability tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from helpers.cli import run, run_text
from helpers.waits import wait_for

logger = logging.getLogger(__name__)


@pytest.mark.smoke
def test_helm_install_and_test(chart_path: Path, kind_cluster: str, cert_manager_ready: str) -> None:
    release = "acko-test"
    ns = "aerospike-operator-test"

    try:
        run(
            [
                "helm",
                "install",
                release,
                str(chart_path),
                "--namespace",
                ns,
                "--create-namespace",
                "--set",
                "image.repository=ghcr.io/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator",
                "--set",
                "image.tag=v0.0.1",
                "--set",
                "image.pullPolicy=Never",
                "--wait",
                "--timeout",
                "5m",
            ],
            timeout=600,
        )

        # `helm test` runs the bundled test pods and blocks until done.
        out = run_text(["helm", "test", release, "-n", ns], timeout=300)
        assert "Phase:" in out and "Succeeded" in out, f"helm test did not report Succeeded:\n{out}"

    finally:
        run(["helm", "uninstall", release, "-n", ns, "--wait", "--timeout", "2m"], check=False)
        run(["kubectl", "delete", "ns", ns, "--ignore-not-found", "--wait=false"], check=False)
        # Best-effort wait so subsequent tests don't trip on a Terminating ns.
        wait_for(
            lambda: run(["kubectl", "get", "ns", ns], check=False, quiet=True).returncode != 0,
            timeout=60,
            interval=2,
            description=f"ns/{ns} fully deleted",
        )
