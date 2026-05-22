"""helm template — 7-mode assertion matrix.

Each mode is one parametrize entry. Tests are pure manifest-shape assertions
that need no Kind cluster, so they run on every PR as a fast gate.

Drift note: chart 0.4.0 removed the legacy `ui.enabled` master switch in
favour of the independent `ui.api.enabled` / `ui.web.enabled` toggles (both
default `true`). Operator-only mode therefore opts out by setting BOTH to
`false`. If a future chart re-introduces a master switch, update the
parametrize entries below.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from helpers.chart_yaml import (
    container_env,
    deployment_names,
    find_kind,
    find_named,
    helm_test_pods,
    network_policy_ports,
    template,
    template_expect_fail,
)


# ---------------------------------------------------------------------------
# Operator-only (UI on by default → opt out via ui.api + ui.web both false)
# ---------------------------------------------------------------------------
@pytest.mark.chart
def test_operator_only_no_ui(chart_path: Path) -> None:
    docs = template(chart_path, {"ui.api.enabled": "false", "ui.web.enabled": "false"})
    deps = deployment_names(docs)

    assert any(name == "foo-aerospike-ce-kubernetes-operator" for name in deps), (
        f"operator Deployment missing from manifest set: {deps}"
    )
    assert not any("ui-api" in name or "ui-web" in name for name in deps), (
        f"UI Deployments present in operator-only mode: {deps}"
    )
    assert not find_kind(docs, "ServiceMonitor"), (
        "ServiceMonitor should NOT be rendered without monitoring.enabled"
    )


# ---------------------------------------------------------------------------
# UI full — api + web together
# ---------------------------------------------------------------------------
@pytest.mark.chart
def test_ui_full_renders_api_web_networkpolicy(chart_path: Path) -> None:
    docs = template(
        chart_path,
        {
            "ui.networkPolicy.enabled": "true",
            "ui.tests.enabled": "true",
        },
    )
    deps = deployment_names(docs)
    assert any(name.endswith("ui-api") for name in deps), f"ui-api missing: {deps}"
    assert any(name.endswith("ui-web") for name in deps), f"ui-web missing: {deps}"

    nps = find_kind(docs, "NetworkPolicy")
    assert nps, "NetworkPolicy not rendered (ui.networkPolicy.enabled=true)"
    ports = network_policy_ports(nps[0])
    assert {8000, 3100} <= ports, f"UI full NetworkPolicy must include both :8000 and :3100, got {ports}"

    assert helm_test_pods(docs), "helm-test pod missing (ui.tests.enabled=true)"


# ---------------------------------------------------------------------------
# UI api-only
# ---------------------------------------------------------------------------
@pytest.mark.chart
def test_ui_api_only_no_web(chart_path: Path) -> None:
    docs = template(
        chart_path,
        {
            "ui.web.enabled": "false",
            "ui.ingress.target": "api",
            "ui.networkPolicy.enabled": "true",
            "ui.tests.enabled": "true",
        },
    )
    deps = deployment_names(docs)
    assert any(name.endswith("ui-api") for name in deps), f"ui-api missing: {deps}"
    assert not any(name.endswith("ui-web") for name in deps), f"ui-web present in api-only: {deps}"

    nps = find_kind(docs, "NetworkPolicy")
    ports = network_policy_ports(nps[0]) if nps else set()
    assert 8000 in ports, f"NetworkPolicy must allow :8000, got {ports}"
    assert 3100 not in ports, f"NetworkPolicy must NOT allow :3100 in api-only, got {ports}"

    assert helm_test_pods(docs), "helm-test pod missing (api enabled, tests enabled)"


# ---------------------------------------------------------------------------
# UI web-only
# ---------------------------------------------------------------------------
@pytest.mark.chart
def test_ui_web_only_no_api(chart_path: Path) -> None:
    docs = template(
        chart_path,
        {
            "ui.api.enabled": "false",
            "ui.web.env.apiUrl": "http://x",
            "ui.networkPolicy.enabled": "true",
            "ui.tests.enabled": "true",
        },
    )
    deps = deployment_names(docs)
    assert any(name.endswith("ui-web") for name in deps), f"ui-web missing: {deps}"
    assert not any(name.endswith("ui-api") for name in deps), f"ui-api present in web-only: {deps}"

    nps = find_kind(docs, "NetworkPolicy")
    ports = network_policy_ports(nps[0]) if nps else set()
    assert 3100 in ports, f"NetworkPolicy must allow :3100, got {ports}"
    assert 8000 not in ports, f"NetworkPolicy must NOT allow :8000 in web-only, got {ports}"

    web_dep = find_named(docs, "Deployment", "foo-aerospike-ce-kubernetes-operator-ui-web")
    assert web_dep is not None
    amst = web_dep["spec"]["template"]["spec"].get("automountServiceAccountToken")
    assert amst is False, (
        "ui-web Pod must have automountServiceAccountToken=false (no K8s API access from web)"
    )

    # api disabled → no test pod (the only helm-test exercises api connectivity)
    assert not helm_test_pods(docs), "helm-test pod must NOT be rendered when api is disabled"


# ---------------------------------------------------------------------------
# OTel disabled (default)
# ---------------------------------------------------------------------------
@pytest.mark.chart
def test_otel_disabled_by_default(chart_path: Path) -> None:
    docs = template(chart_path, {})
    api = find_named(docs, "Deployment", "foo-aerospike-ce-kubernetes-operator-ui-api")
    assert api is not None
    env_vars = container_env(api, "api")

    assert env_vars.get("OTEL_SDK_DISABLED") == "true", (
        f"default OTEL_SDK_DISABLED must be 'true', got {env_vars.get('OTEL_SDK_DISABLED')}"
    )
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in env_vars, (
        "OTEL_EXPORTER_OTLP_ENDPOINT must not leak in when otel is off"
    )


# ---------------------------------------------------------------------------
# OTel enabled — env wiring contract (cluster-manager #265 prereq)
# ---------------------------------------------------------------------------
@pytest.mark.chart
def test_otel_enabled_env_wiring(chart_path: Path) -> None:
    docs = template(
        chart_path,
        {
            "ui.api.otel.enabled": "true",
            "ui.api.otel.endpoint": "http://col:4317",
        },
    )
    api = find_named(docs, "Deployment", "foo-aerospike-ce-kubernetes-operator-ui-api")
    assert api is not None
    env_vars = container_env(api, "api")

    assert env_vars.get("OTEL_SDK_DISABLED") == "false"
    assert env_vars.get("OTEL_EXPORTER_OTLP_ENDPOINT") == "http://col:4317"
    assert env_vars.get("OTEL_TRACES_SAMPLER"), "OTEL_TRACES_SAMPLER must be set"
    assert env_vars.get("OTEL_SERVICE_NAME"), "OTEL_SERVICE_NAME must be set"


# ---------------------------------------------------------------------------
# ingress.target failfast — chart MUST refuse incompatible combos (since #236)
# ---------------------------------------------------------------------------
@pytest.mark.chart
def test_ingress_target_web_with_web_disabled_fails(chart_path: Path) -> None:
    err = template_expect_fail(
        chart_path,
        {
            "ui.web.enabled": "false",
            "ui.ingress.enabled": "true",
            # default ingress.target=web → conflicts with web.enabled=false
        },
    )
    assert "ui.ingress.target" in err, f"failfast error should mention ui.ingress.target, got:\n{err}"
