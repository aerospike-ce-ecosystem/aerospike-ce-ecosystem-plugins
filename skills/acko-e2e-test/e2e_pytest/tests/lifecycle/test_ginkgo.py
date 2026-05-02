"""Wrapper around the in-tree Ginkgo suite (`go test ./test/e2e/`).

We invoke `go test` directly instead of `make test-e2e` because the latter
runs `cleanup-test-e2e` at the end (deletes the Kind cluster), which would
invalidate every test scheduled after this one.

Mode is selected via env var GINKGO_MODE (smoke|full|heavy|focus:<re>):
  pytest -m full GINKGO_MODE=full     → full suite (~15–30 min)
  pytest -m full GINKGO_MODE=heavy    → heavy lane only
  pytest -m full GINKGO_MODE=focus:Multi-rack
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

from helpers import env

logger = logging.getLogger(__name__)


def _ginkgo_args(mode: str) -> list[str]:
    if mode == "full":
        return []
    if mode == "smoke":
        return ["-ginkgo.label-filter=!heavy"]
    if mode == "heavy":
        return ["-ginkgo.label-filter=heavy"]
    if mode.startswith("focus:"):
        return [f"-ginkgo.focus={mode.removeprefix('focus:')}"]
    raise ValueError(f"unknown GINKGO_MODE={mode!r} (full|smoke|heavy|focus:<re>)")


@pytest.mark.full
def test_ginkgo_suite(operator_repo: Path, kind_cluster: str, cert_manager_ready: str) -> None:
    mode = os.environ.get("GINKGO_MODE", "full")
    extra = _ginkgo_args(mode)
    cmd = [
        "go",
        "test",
        "-tags=e2e",
        "-timeout",
        "60m",
        "./test/e2e/",
        "-v",
        "-ginkgo.v",
        *extra,
    ]
    logger.info("$ %s (mode=%s)", " ".join(cmd), mode)

    log_path = Path("/tmp") / f"ginkgo-{mode.replace(':', '-')}.log"
    started = time.monotonic()
    with log_path.open("w") as out_f:
        proc = subprocess.run(
            cmd,
            cwd=operator_repo,
            env={
                **os.environ,
                "KIND": "kind",
                "KIND_CLUSTER": env.KIND_CLUSTER,
                "CONTAINER_TOOL": env.CONTAINER_TOOL,
                "KIND_PROVIDER": env.KIND_PROVIDER,
                "KIND_EXPERIMENTAL_PROVIDER": env.KIND_PROVIDER,
            },
            stdout=out_f,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=4000,
        )
    elapsed = time.monotonic() - started

    log_text = log_path.read_text(errors="replace")
    ran_match = re.search(r"^Ran (\d+) of (\d+) Specs", log_text, flags=re.MULTILINE)
    fails = log_text.count("FAIL!")

    logger.info("ginkgo: rc=%d elapsed=%.1fs fails=%d (log: %s)", proc.returncode, elapsed, fails, log_path)
    if ran_match:
        logger.info("ginkgo: %s", ran_match.group(0))

    assert proc.returncode == 0, f"go test exited {proc.returncode} (log: {log_path})"
    assert fails == 0, f"{fails} FAIL! lines in log: {log_path}"
    assert ran_match, f"could not find 'Ran N of N Specs' line in {log_path}"
