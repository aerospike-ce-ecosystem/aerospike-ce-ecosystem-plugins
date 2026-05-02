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

# Paths — operator repo and chart. Default assumes the workspace layout
# (asc-workspace/aerospike-ce-kubernetes-operator alongside the plugins repo).
# helpers/env.py → parents: helpers, e2e_pytest, acko-e2e-test, skills,
# aerospike-ce-ecosystem-plugins, asc-workspace (parent #5).
_DEFAULT_OPERATOR_REPO = Path(__file__).resolve().parents[5] / "aerospike-ce-kubernetes-operator"
OPERATOR_REPO = Path(_env("OPERATOR_REPO", str(_DEFAULT_OPERATOR_REPO)))
CHART_PATH = Path(_env("CHART_PATH", str(OPERATOR_REPO / "charts" / "aerospike-ce-kubernetes-operator")))


def env_for_kind() -> dict[str, str]:
    """Env vars to splice into subprocess.run when calling kind/make."""
    return {
        "KIND_CLUSTER": KIND_CLUSTER,
        "CONTAINER_TOOL": CONTAINER_TOOL,
        "KIND_PROVIDER": KIND_PROVIDER,
        "KIND_EXPERIMENTAL_PROVIDER": KIND_PROVIDER,
    }
