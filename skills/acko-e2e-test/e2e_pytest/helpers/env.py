"""Environment defaults shared across helpers and fixtures.

Every value can be overridden via environment variable. Defaults match the
ACKO project's hardcoded values so scripts compose without surprises.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


# Kind cluster + container runtime
KIND_CLUSTER = _env("KIND_CLUSTER", "aerospike-ce-kubernetes-operator-test-e2e")
CONTAINER_TOOL = _env("CONTAINER_TOOL", "podman")
KIND_PROVIDER = _env("KIND_PROVIDER", "podman")

# Namespaces
NS_OPERATOR = _env("NS_OPERATOR", "aerospike-operator")
NS_AEROSPIKE = _env("NS_AEROSPIKE", "aerospike")
NS_OTEL = _env("NS_OTEL", "otel")
NS_CERT_MANAGER = _env("NS_CERT_MANAGER", "cert-manager")

# Helm
HELM_RELEASE = _env("HELM_RELEASE", "acko")

# Images.
# IMG matches test/e2e/e2e_suite_test.go:47 — BeforeSuite hardcodes this tag.
# Pre-loading any other tag is wasted work because Ginkgo will rebuild and
# re-load with v0.0.1 anyway.
IMG = _env("IMG", "ghcr.io/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator:v0.0.1")
API_IMG = _env("API_IMG", "ghcr.io/aerospike-ce-ecosystem/aerospike-cluster-manager-api:latest")
COLLECTOR_IMAGE = _env("COLLECTOR_IMAGE", "docker.io/otel/opentelemetry-collector-contrib:latest")
CERT_MANAGER_VERSION = _env("CERT_MANAGER_VERSION", "v1.19.3")


# Paths — operator repo and chart.
# Discovery order (first existing dir wins):
#   1. $OPERATOR_REPO env var
#   2. workspace sibling layout (this plugin under a shared workspace directory)
#   3. CWD/aerospike-ce-kubernetes-operator (run from a parent dir that holds both)
#   4. ~/aerospike-ce-kubernetes-operator (cloned to home)
#   5. ~/github/aerospike-ce-kubernetes-operator (the default ~/github/<repo> layout)
#   6. /workspace/aerospike-ce-kubernetes-operator (devcontainer / GitHub Codespaces style)
# If none found, OPERATOR_REPO points at candidate #2 anyway and tests that
# require it will pytest.skip() with a helpful message — no hard failure
# from import time.
def _discover_operator_repo() -> Path:
    explicit = os.environ.get("OPERATOR_REPO")
    if explicit:
        return Path(explicit).expanduser()

    here = Path(__file__).resolve()
    # parents: helpers, e2e_pytest, acko-e2e-test, skills, plugin repo, shared workspace
    workspace_sibling = here.parents[5] / "aerospike-ce-kubernetes-operator"

    candidates = [
        workspace_sibling,
        Path.cwd() / "aerospike-ce-kubernetes-operator",
        Path.home() / "aerospike-ce-kubernetes-operator",
        Path.home() / "github" / "aerospike-ce-kubernetes-operator",
        Path("/workspace/aerospike-ce-kubernetes-operator"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    # Nothing found — return the workspace-sibling guess so error messages
    # at fixture-skip time point at the conventional location.
    return workspace_sibling


OPERATOR_REPO = _discover_operator_repo()
CHART_PATH = Path(_env("CHART_PATH", str(OPERATOR_REPO / "charts" / "aerospike-ce-kubernetes-operator")))


def env_for_kind() -> dict[str, str]:
    """Env vars to splice into subprocess.run when calling kind/make."""
    return {
        "KIND_CLUSTER": KIND_CLUSTER,
        "CONTAINER_TOOL": CONTAINER_TOOL,
        "KIND_PROVIDER": KIND_PROVIDER,
        "KIND_EXPERIMENTAL_PROVIDER": KIND_PROVIDER,
    }
