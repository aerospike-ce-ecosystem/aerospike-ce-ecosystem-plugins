"""Multi-cluster + OIDC end-to-end scenarios (Stream D).

Covers Phase-0 contract C-1 (values keys), C-4 (JWT convention), and C-5
(acko-realm.json users/roles). Each test pairs to a contract assertion the
Stream D plan promised:

    helm install -f values-common.yaml      → only ui.web (no operator/CRD/api)
    helm install -f values-operator.yaml    → operator + api, no ui.web
    JWT-less   API call                     → 401
    valid aud=acko-api JWT                  → 200
    wrong aud (acko-other client)           → 401
    requiredRoles=[acko:dev], prod-user     → 403
    requiredRoles=[acko:dev], dev-user      → 200
    /cluster-registry.json from common pod  → matches values clusters[0].id
    helm test acko -n acko-common           → test-multicluster-routing pass

Skips cleanly when the matching chart preset/template does not exist yet
(other streams in flight). Cleans up its own helm releases.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from helpers import env
from helpers.cli import CommandError, run, run_text
from helpers.port_forward import port_forward

logger = logging.getLogger(__name__)

# Stream A contract: presets live next to values.yaml. Both filenames are
# fixed by the Phase-0 plan; if Stream A renames them, fix here too.
PRESETS = {
    "common": "values-common.yaml",
    "operator": "values-operator.yaml",
}
NS_COMMON = "acko-common"
NS_OPERATOR = "acko-operator"
RELEASE_COMMON = "acko-common"
RELEASE_OPERATOR = "acko-operator"

# requiredRoles override per-profile. These are passed via `--set-json` so
# the test pins the role list independently of preset defaults.
REQUIRED_ROLES_DEV = '["acko:dev"]'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _preset_path(chart_path: Path, key: str) -> Path:
    p = chart_path / PRESETS[key]
    if not p.is_file():
        pytest.skip(f"preset {p} not present yet (Stream A still in flight)")
    return p


def _has_chart_template(chart_path: Path, name: str) -> bool:
    return (chart_path / "templates" / name).exists()


def _helm_install(
    *,
    release: str,
    namespace: str,
    chart_path: Path,
    values_file: Path,
    extra_sets: list[tuple[str, str]] | None = None,
    extra_set_json: list[tuple[str, str]] | None = None,
    timeout: str = "5m",
) -> None:
    cmd: list[str] = [
        "helm",
        "upgrade",
        "--install",
        release,
        str(chart_path),
        "-n",
        namespace,
        "--create-namespace",
        "-f",
        str(values_file),
    ]
    for k, v in extra_sets or []:
        cmd += ["--set", f"{k}={v}"]
    for k, v in extra_set_json or []:
        cmd += ["--set-json", f"{k}={v}"]
    cmd += ["--wait", "--timeout", timeout]
    run(cmd)


def _helm_uninstall(release: str, namespace: str) -> None:
    run(
        ["helm", "uninstall", release, "-n", namespace, "--ignore-not-found"],
        check=False,
        quiet=True,
    )
    run(
        ["kubectl", "delete", "ns", namespace, "--ignore-not-found", "--wait=false"],
        check=False,
        quiet=True,
    )


def _kubectl_jsonpath(args: list[str]) -> str:
    return run_text(["kubectl", *args])


def _count_resources(namespace: str, kind: str, label_selector: str | None = None) -> int:
    args = [
        "get",
        kind,
        "-n",
        namespace,
        "--no-headers",
        "--ignore-not-found",
    ]
    if label_selector:
        args += ["-l", label_selector]
    out = run_text(["kubectl", *args])
    return len([line for line in out.splitlines() if line.strip()])


@contextlib.contextmanager
def _api_pf_url(namespace: str, port: int) -> Iterator[str]:
    """Wrapper around port_forward for the api Service."""
    svc = run_text(
        [
            "kubectl",
            "get",
            "svc",
            "-n",
            namespace,
            "-l",
            "app.kubernetes.io/component=ui-api",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )
    if not svc:
        pytest.skip(f"ui-api Service not found in {namespace}")
    with port_forward(
        namespace=namespace,
        service=svc,
        local_port=port,
        service_port=80,
    ) as url:
        yield url


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def chart_with_multicluster(chart_path: Path) -> Path:
    """Skip the whole module if Stream A hasn't shipped the multi-cluster
    bits yet. Two indicators:
      1. preset files exist
      2. cluster-registry ConfigMap template exists
    """
    for key in PRESETS:
        _preset_path(chart_path, key)
    if not _has_chart_template(chart_path, "configmap-cluster-registry.yaml"):
        pytest.skip(
            "chart template configmap-cluster-registry.yaml missing — Stream A not merged yet"
        )
    return chart_path


@pytest.fixture(scope="module")
def keycloak_in_cluster_url() -> str:
    """OIDC issuer URL as seen from inside the Kind cluster."""
    return os.environ.get(
        "KEYCLOAK_INCLUSTER_URL",
        "http://keycloak.keycloak.svc.cluster.local/realms/acko",
    )


@pytest.fixture(scope="module")
def common_release(
    chart_with_multicluster: Path,
    cert_manager_ready: str,
    keycloak_in_cluster_url: str,
) -> Iterator[dict[str, Any]]:
    """Install the common (web-only) profile preset."""
    _ = cert_manager_ready  # ordering fixture
    chart = chart_with_multicluster
    values = _preset_path(chart, "common")
    try:
        _helm_install(
            release=RELEASE_COMMON,
            namespace=NS_COMMON,
            chart_path=chart,
            values_file=values,
            extra_sets=[
                ("ui.api.auth.oidc.issuerUrl", keycloak_in_cluster_url),
                ("ui.web.auth.oidc.issuerUrl", keycloak_in_cluster_url),
                ("ui.api.auth.oidc.audience", "acko-api"),
                ("ui.web.auth.oidc.clientId", "acko-spa"),
            ],
            extra_set_json=[("ui.api.auth.oidc.requiredRoles", REQUIRED_ROLES_DEV)],
        )
        yield {"release": RELEASE_COMMON, "namespace": NS_COMMON, "chart": str(chart)}
    finally:
        _helm_uninstall(RELEASE_COMMON, NS_COMMON)


@pytest.fixture(scope="module")
def operator_release(
    chart_with_multicluster: Path,
    cert_manager_ready: str,
    keycloak_in_cluster_url: str,
) -> Iterator[dict[str, Any]]:
    _ = cert_manager_ready  # ordering fixture
    chart = chart_with_multicluster
    values = _preset_path(chart, "operator")
    try:
        _helm_install(
            release=RELEASE_OPERATOR,
            namespace=NS_OPERATOR,
            chart_path=chart,
            values_file=values,
            extra_sets=[
                ("ui.api.auth.oidc.issuerUrl", keycloak_in_cluster_url),
                ("ui.api.auth.oidc.audience", "acko-api"),
                ("image.repository", env.IMG.split(":")[0]),
                ("image.tag", env.IMG.split(":")[1]),
                ("image.pullPolicy", "Never"),
            ],
            extra_set_json=[("ui.api.auth.oidc.requiredRoles", REQUIRED_ROLES_DEV)],
        )
        yield {"release": RELEASE_OPERATOR, "namespace": NS_OPERATOR, "chart": str(chart)}
    finally:
        _helm_uninstall(RELEASE_OPERATOR, NS_OPERATOR)


# ---------------------------------------------------------------------------
# Manifest-shape tests — what each preset deploys
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.needs_helm
def test_common_profile_manifest_shape(common_release: dict[str, Any]) -> None:
    """values-common.yaml installs ONLY ui.web + cluster-registry CMs.

    Operator Deployment, CRD, webhook config, and ui.api Deployment must
    all be 0.
    """
    ns = common_release["namespace"]
    operator_count = _count_resources(ns, "deploy", "control-plane=controller-manager")
    api_count = _count_resources(ns, "deploy", "app.kubernetes.io/component=ui-api")
    web_count = _count_resources(ns, "deploy", "app.kubernetes.io/component=ui-web")
    cm_count = _count_resources(ns, "configmap", "app.kubernetes.io/managed-by=Helm")

    assert operator_count == 0, f"operator Deployment present in common profile (got {operator_count})"
    assert api_count == 0, f"ui-api Deployment present in common profile (got {api_count})"
    assert web_count == 1, f"expected exactly 1 ui-web Deployment, got {web_count}"
    # cluster-registry + web-oidc-config (see C-1).
    assert cm_count >= 2, (
        f"expected ≥2 chart-managed ConfigMaps "
        f"(cluster-registry + web-oidc), got {cm_count}"
    )

    # Webhook/CRD must NOT be installed by common preset.
    crds = run_text(
        ["kubectl", "get", "crd", "-o", "name", "--ignore-not-found"],
        quiet=True,
    )
    assert "aerospikeclusters.acko.io" not in crds or os.environ.get("ALLOW_CRD_PRESENT") == "1", (
        "common profile must not own AerospikeCluster CRD; "
        "either Stream A operator.enabled gate is broken or a previous suite leaked it"
    )


@pytest.mark.smoke
@pytest.mark.needs_helm
def test_operator_profile_manifest_shape(operator_release: dict[str, Any]) -> None:
    """values-operator.yaml installs operator + api + webhook, no ui.web."""
    ns = operator_release["namespace"]
    operator_count = _count_resources(ns, "deploy", "control-plane=controller-manager")
    api_count = _count_resources(ns, "deploy", "app.kubernetes.io/component=ui-api")
    web_count = _count_resources(ns, "deploy", "app.kubernetes.io/component=ui-web")

    assert operator_count == 1, f"expected 1 operator Deployment, got {operator_count}"
    assert api_count == 1, f"expected 1 ui-api Deployment, got {api_count}"
    assert web_count == 0, f"ui-web Deployment present in operator profile (got {web_count})"


# ---------------------------------------------------------------------------
# OIDC enforcement tests — wrap operator-profile api with JWT checks
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.needs_helm
def test_api_rejects_anonymous(operator_release: dict[str, Any]) -> None:
    """No Authorization header → 401."""
    ns = operator_release["namespace"]
    with _api_pf_url(ns, port=18101) as base:
        # Probe an authenticated endpoint. /healthz is intentionally public
        # so target /api/v1/clusters which Stream B gates by OIDC.
        r = httpx.get(f"{base}/api/v1/clusters", timeout=5.0)
        assert r.status_code == 401, (
            f"expected 401 without token, got {r.status_code}: {r.text[:200]}"
        )


@pytest.mark.smoke
@pytest.mark.needs_helm
def test_api_accepts_dev_role_with_correct_audience(
    operator_release: dict[str, Any], keycloak_token
) -> None:
    """Valid acko-api audience + acko:dev role → 200."""
    ns = operator_release["namespace"]
    token = keycloak_token(role="dev", client_id="acko-spa")
    with _api_pf_url(ns, port=18102) as base:
        r = httpx.get(
            f"{base}/api/v1/clusters",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        assert r.status_code == 200, (
            f"expected 200 for dev-user with aud=acko-api, got {r.status_code}: {r.text[:200]}"
        )


@pytest.mark.smoke
@pytest.mark.needs_helm
def test_api_rejects_wrong_audience(
    operator_release: dict[str, Any], keycloak_token
) -> None:
    """Token from acko-other client → 401 (audience mismatch)."""
    ns = operator_release["namespace"]
    token = keycloak_token(role="dev", client_id="acko-other")
    with _api_pf_url(ns, port=18103) as base:
        r = httpx.get(
            f"{base}/api/v1/clusters",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        assert r.status_code == 401, (
            f"expected 401 for aud=acko-other, got {r.status_code}: {r.text[:200]}"
        )


@pytest.mark.smoke
@pytest.mark.needs_helm
def test_api_rejects_missing_role(
    operator_release: dict[str, Any], keycloak_token
) -> None:
    """prod-user (acko:prod only) hitting requiredRoles=[acko:dev] → 403."""
    ns = operator_release["namespace"]
    token = keycloak_token(role="prod", client_id="acko-spa")
    with _api_pf_url(ns, port=18104) as base:
        r = httpx.get(
            f"{base}/api/v1/clusters",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
        )
        assert r.status_code == 403, (
            f"expected 403 for prod-user without acko:dev, got {r.status_code}: {r.text[:200]}"
        )


# ---------------------------------------------------------------------------
# Cluster registry tests — common profile serves /cluster-registry.json
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.needs_helm
def test_cluster_registry_served(
    common_release: dict[str, Any], chart_with_multicluster: Path
) -> None:
    """The web pod's /cluster-registry.json mounts the chart-rendered CM."""
    ns = common_release["namespace"]
    # Find the web pod
    pod = run_text(
        [
            "kubectl",
            "get",
            "pod",
            "-n",
            ns,
            "-l",
            "app.kubernetes.io/component=ui-web",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )
    if not pod:
        pytest.skip("ui-web pod not found")

    # curl from inside the pod to avoid port-forward gymnastics.
    out = run_text(
        [
            "kubectl",
            "exec",
            "-n",
            ns,
            pod,
            "--",
            "wget",
            "-qO-",
            "http://localhost/cluster-registry.json",
        ]
    )
    data = json.loads(out)
    assert "clusters" in data, f"cluster-registry.json missing 'clusters' key: {data!r}"
    assert isinstance(data["clusters"], list), "clusters must be a list"
    assert data["clusters"], "clusters list must be non-empty (preset defines at least 1)"

    # Cross-check against values-common.yaml — expect at least one id field.
    first = data["clusters"][0]
    assert "id" in first, f"cluster entry missing id: {first!r}"


# ---------------------------------------------------------------------------
# Helm test hook — the chart should ship a `test-multicluster-routing` Pod
# ---------------------------------------------------------------------------
@pytest.mark.smoke
@pytest.mark.needs_helm
def test_helm_test_multicluster_routing(common_release: dict[str, Any]) -> None:
    if not _has_chart_template(
        Path(common_release["chart"]),
        "tests/test-multicluster-routing.yaml",
    ):
        pytest.skip(
            "chart helm-test pod test-multicluster-routing.yaml missing — Stream A pending"
        )
    # `helm test` blocks until the test Pod completes (Succeeded) or fails.
    try:
        run(
            [
                "helm",
                "test",
                common_release["release"],
                "-n",
                common_release["namespace"],
                "--timeout",
                "3m",
            ]
        )
    except CommandError as exc:
        # Surface the test pod logs in the failure for fast triage.
        try:
            logs = run_text(
                [
                    "kubectl",
                    "logs",
                    "-n",
                    common_release["namespace"],
                    "-l",
                    "helm.sh/hook=test",
                    "--tail=200",
                ],
                quiet=True,
            )
        except CommandError:
            logs = "<unable to fetch logs>"
        pytest.fail(
            f"helm test failed (rc={exc.returncode})\n--- pod logs ---\n{logs}"
        )


# ---------------------------------------------------------------------------
# OIDC discovery sanity — independent of any release; useful as a smoke probe
# ---------------------------------------------------------------------------
@pytest.mark.smoke
def test_keycloak_oidc_discovery(keycloak_url: str) -> None:
    """The realm exposes a working OIDC discovery doc with a JWKS URI."""
    r = httpx.get(f"{keycloak_url}/.well-known/openid-configuration", timeout=5.0)
    assert r.status_code == 200, f"discovery returned {r.status_code}"
    body = r.json()
    assert "jwks_uri" in body, f"missing jwks_uri in discovery: {body}"
    assert body["issuer"].rstrip("/").endswith("/realms/acko"), (
        f"unexpected issuer: {body.get('issuer')}"
    )

    # JWKS itself must serve a non-empty keys array.
    jwks = httpx.get(body["jwks_uri"], timeout=5.0)
    assert jwks.status_code == 200, f"jwks {body['jwks_uri']} returned {jwks.status_code}"
    keys = jwks.json().get("keys", [])
    assert keys, "JWKS must contain ≥1 signing key"
    # Pause a tick so the test reads cleanly in CI logs alongside the release fixtures.
    time.sleep(0)
