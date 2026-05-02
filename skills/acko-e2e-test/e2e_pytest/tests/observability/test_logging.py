"""Logging contracts: text default → JSON upgrade → X-Request-ID correlation.

The first test runs against the chart default (text). The second/third
helm-upgrade the release to LOG_FORMAT=json so subsequent observability
tests (test_otel_runtime.py) inherit the JSON-enabled state.
"""

from __future__ import annotations

import json
import logging
import re
import time

import pytest

from helpers import env
from helpers.api_client import ApiClient
from helpers.cli import run, run_text

logger = logging.getLogger(__name__)


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


def _api_logs(since: str = "30s") -> str:
    pod = _ui_api_pod()
    return run_text(
        [
            "kubectl",
            "logs",
            "-n",
            env.NS_OPERATOR,
            pod,
            "-c",
            "api",
            f"--since={since}",
        ],
        check=False,
    )


@pytest.mark.smoke
def test_default_log_format_is_text(helm_release: dict, api: ApiClient) -> None:
    """Default install: API logs are text-formatted (`YYYY-... LEVEL [logger] msg`)."""
    pod = _ui_api_pod()
    cur_fmt = run_text(
        [
            "kubectl",
            "exec",
            "-n",
            env.NS_OPERATOR,
            pod,
            "-c",
            "api",
            "--",
            "printenv",
            "LOG_FORMAT",
        ],
        check=False,
    )
    if cur_fmt and cur_fmt != "text":
        pytest.skip(
            f"LOG_FORMAT={cur_fmt!r} (already non-text — text-default test re-runs after fresh install)"
        )

    # Make a request so we get a fresh log line
    api.get("/api/health")
    time.sleep(1)
    sample = _api_logs(since="10s")
    assert re.search(r"\d{4}-\d{2}-\d{2}.*INFO.*\[", sample), (
        f"no text-format log line seen in last 10s sample:\n{sample}"
    )


@pytest.mark.smoke
def test_log_format_json_after_upgrade(helm_release: dict) -> None:
    """`helm upgrade --set ui.env.logFormat=json` switches every log line to JSON."""
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

    # Trigger a log line
    pod = _ui_api_pod()
    # Open a quick port-forward via kubectl exec (avoid creating yet another fixture-managed PF)
    # — instead just exercise from inside the pod's loopback.
    run(
        [
            "kubectl",
            "exec",
            "-n",
            env.NS_OPERATOR,
            pod,
            "-c",
            "api",
            "--",
            "curl",
            "-sS",
            "-o",
            "/dev/null",
            "http://localhost:8000/api/health",
        ]
    )
    time.sleep(2)

    sample = _api_logs(since="20s")
    json_lines = [
        ln
        for ln in sample.splitlines()
        if ln.strip().startswith("{") and '"timestamp"' in ln and '"request_id"' in ln
    ]
    assert json_lines, f"no JSON log line found in:\n{sample[-2000:]}"

    one = json.loads(json_lines[0])
    for required in ("timestamp", "level", "logger", "message", "request_id"):
        assert required in one, f"JSON log line missing key {required!r}: {one}"


@pytest.mark.smoke
def test_x_request_id_correlation(helm_release: dict, api: ApiClient) -> None:
    """`X-Request-ID` header is echoed in the response AND embedded in the JSON log record."""
    rid = f"probe-pytest-{int(time.time_ns())}"
    r = api.get("/api/health", headers={"X-Request-ID": rid})
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == rid

    time.sleep(2)
    sample = _api_logs(since="10s")
    found = [ln for ln in sample.splitlines() if rid in ln]
    assert found, f"no log line mentions {rid!r}:\n{sample[-1000:]}"

    one = json.loads(found[0])
    assert one.get("request_id") == rid, f"log line found but request_id field != {rid!r}: {one}"
