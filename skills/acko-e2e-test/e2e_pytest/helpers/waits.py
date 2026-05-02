"""Polling helpers — `kubectl wait` covers Conditions, but lots of our
contracts are about CR fields like .status.phase that aren't Conditions.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from .cli import run

logger = logging.getLogger(__name__)


def wait_for(
    predicate: Callable[[], bool],
    *,
    timeout: float = 180,
    interval: float = 2,
    description: str = "condition",
) -> None:
    """Poll predicate until True or timeout. Raises TimeoutError on miss."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except Exception as e:
            logger.debug("predicate raised %s, continuing to poll", e)
        time.sleep(interval)
    raise TimeoutError(f"timed out after {timeout}s waiting for {description}")


def asc_phase(name: str, namespace: str) -> str:
    proc = run(
        ["kubectl", "get", "asc", name, "-n", namespace, "-o", "jsonpath={.status.phase}"],
        check=False,
        quiet=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def wait_asc_completed(name: str, namespace: str, *, timeout: int = 300) -> None:
    wait_for(
        lambda: asc_phase(name, namespace) == "Completed",
        timeout=timeout,
        interval=5,
        description=f"asc/{name} in ns/{namespace} reaching Completed",
    )


def asc_status(name: str, namespace: str) -> dict:
    proc = run(["kubectl", "get", "asc", name, "-n", namespace, "-o", "json"])
    return json.loads(proc.stdout).get("status", {})


def wait_asc_gone(name: str, namespace: str, *, timeout: int = 120) -> None:
    """Wait for `kubectl get asc <name>` to return non-zero (CR removed)."""

    def gone() -> bool:
        proc = run(["kubectl", "get", "asc", name, "-n", namespace], check=False, quiet=True)
        return proc.returncode != 0

    wait_for(gone, timeout=timeout, interval=2, description=f"asc/{name} in ns/{namespace} to be removed")
