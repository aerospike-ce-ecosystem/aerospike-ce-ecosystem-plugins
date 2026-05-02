"""OTel runtime export — regression guard for cluster-manager #265.

Before #265 only asyncpg child spans reached the collector, parent-less,
because FastAPIInstrumentor was never invoked. This test enables the OTel
toggle, deploys an OTel collector with a debug exporter, generates traffic,
and asserts that **both** instrumentation scopes appear AND that at least
one trace contains a Server-kind FastAPI span and an asyncpg child span
sharing the trace ID.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pytest

from helpers import env
from helpers.api_client import ApiClient
from helpers.cli import run, run_text
from helpers.otel_log import find_correlated_traces, parse_collector_log
from helpers.port_forward import port_forward

logger = logging.getLogger(__name__)
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
COLLECTOR_YAML = Path(__file__).resolve().parents[3] / "reference" / "otel-collector.yaml"


def _ui_api_pod() -> str:
    return run_text(
        [
            "kubectl",
            "get",
            "pod",
            "-n",
            env.NS_OPERATOR,
            "-l",
            "app.kubernetes.io/component=ui-api",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )


def _api_pod_envs() -> dict[str, str]:
    pod = _ui_api_pod()
    raw = run_text(["kubectl", "exec", "-n", env.NS_OPERATOR, pod, "-c", "api", "--", "printenv"])
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


@pytest.fixture(scope="module")
def otel_collector(kind_cluster: str) -> str:
    """Apply the bundled collector manifest and patch its image to a tag we can pull.

    The bundled YAML pins an older collector version that has occasionally
    been rotated out of docker.io. We resolve this by hot-loading the
    `:latest` tag into Kind and overriding the image on the Deployment.
    """
    if not COLLECTOR_YAML.exists():
        pytest.skip(f"collector manifest missing: {COLLECTOR_YAML}")

    run(["kubectl", "apply", "-f", str(COLLECTOR_YAML)])

    # Try the original image first; if it doesn't come up in 60s, hot-swap.
    avail = run(
        [
            "kubectl",
            "wait",
            "deploy/otel-collector",
            "--for=condition=Available",
            "-n",
            env.NS_OTEL,
            "--timeout=60s",
        ],
        check=False,
        quiet=True,
    )

    if avail.returncode != 0:
        logger.warning(
            "collector did not come up with the manifest's pinned tag — patching to %s", env.COLLECTOR_IMAGE
        )
        run(["bash", str(SCRIPTS / "load-image.sh"), env.COLLECTOR_IMAGE], timeout=300)
        run(
            [
                "kubectl",
                "set",
                "image",
                "-n",
                env.NS_OTEL,
                "deploy/otel-collector",
                f"collector={env.COLLECTOR_IMAGE}",
            ]
        )
        run(
            [
                "kubectl",
                "patch",
                "deploy",
                "-n",
                env.NS_OTEL,
                "otel-collector",
                "--type=json",
                '-p=[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Never"}]',
            ]
        )
        run(
            [
                "kubectl",
                "rollout",
                "status",
                "-n",
                env.NS_OTEL,
                "deploy/otel-collector",
                "--timeout=2m",
            ]
        )

    return f"http://otel-collector.{env.NS_OTEL}.svc.cluster.local:4317"


@pytest.mark.smoke
@pytest.mark.regression_guard
def test_otel_runtime_emits_correlated_traces(
    helm_release: dict,
    otel_collector: str,
) -> None:
    # NOTE: we DON'T take the `api` fixture here — that fixture opens the
    # port-forward eagerly (function-scope setup). The helm upgrade below
    # rolls out a new ui-api pod, breaking the existing PF. So we open the
    # PF inline AFTER the upgrade, after `kubectl rollout status` completes.
    # ---- 1. Upgrade chart to enable OTel pointed at the collector ----
    run(
        [
            "helm",
            "upgrade",
            helm_release["release"],
            str(env.CHART_PATH),
            "--namespace",
            helm_release["namespace"],
            "--reuse-values",
            "--set",
            "ui.env.logFormat=json",
            "--set",
            "ui.api.otel.enabled=true",
            "--set",
            f"ui.api.otel.endpoint={otel_collector}",
            "--set",
            "ui.api.otel.protocol=grpc",
            "--wait",
            "--timeout",
            "3m",
        ],
        timeout=300,
    )
    run(
        [
            "kubectl",
            "rollout",
            "status",
            "-n",
            helm_release["namespace"],
            "deploy",
            "--timeout=2m",
        ]
    )

    # ---- 2. Verify env wiring on the new pod ----
    envs = _api_pod_envs()
    assert envs.get("OTEL_SDK_DISABLED") == "false"
    assert envs.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").startswith("http://otel-collector")
    assert envs.get("OTEL_EXPORTER_OTLP_PROTOCOL") == "grpc"
    assert envs.get("OTEL_SERVICE_NAME") == "aerospike-cluster-manager-api"
    assert envs.get("OTEL_TRACES_SAMPLER"), "OTEL_TRACES_SAMPLER not set"

    # ---- 3. Generate traffic (open PF AFTER the rollout finished) ----
    ui_svc = run_text(
        [
            "kubectl",
            "get",
            "svc",
            "-n",
            helm_release["namespace"],
            "-l",
            "app.kubernetes.io/component=ui-api",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ]
    )
    with (
        port_forward(
            namespace=helm_release["namespace"],
            service=ui_svc,
            local_port=18000,
            service_port=80,
        ) as base_url,
        ApiClient(base_url) as api,
    ):
        for _ in range(5):
            api.get("/api/health")
            api.get("/api/v1/connections")
            api.get("/api/openapi.json")
    # Let the BatchSpanProcessor flush
    time.sleep(8)

    # ---- 4. Pull collector logs and parse ----
    log_text = run_text(
        [
            "kubectl",
            "logs",
            "-n",
            env.NS_OTEL,
            "deploy/otel-collector",
            "--since=120s",
        ]
    )

    assert "service.name: Str(aerospike-cluster-manager-api)" in log_text, (
        "no resource span with service.name=aerospike-cluster-manager-api"
    )

    spans = parse_collector_log(log_text)
    scopes = {s.scope for s in spans}
    fastapi_seen = any("fastapi" in scope for scope in scopes)
    asyncpg_seen = any("asyncpg" in scope for scope in scopes)

    assert fastapi_seen, (
        "no opentelemetry.instrumentation.fastapi scope — this is the cluster-manager #265 regression marker"
    )
    assert asyncpg_seen, "no opentelemetry.instrumentation.asyncpg scope"

    # ---- 5. The contract: parent HTTP span + asyncpg child sharing trace id ----
    correlated = find_correlated_traces(spans)
    assert correlated, (
        "no trace contains BOTH a Server-kind FastAPI span and an asyncpg span "
        "sharing the trace id — HTTP→DB context propagation is broken"
    )
    logger.info("correlated traces: %s", correlated[:3])
