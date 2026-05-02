"""Subprocess wrappers — every CLI tool we drive (kubectl/helm/kind/podman/go)
goes through these so behaviour, logging, and error handling stay uniform.

Why we don't import the kubernetes Python client everywhere: the e2e contracts
are about the user-facing CLIs (helm install, kubectl apply, kind load).
Driving the same binaries the user runs catches packaging/CLI regressions
that the in-process client would mask.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

logger = logging.getLogger(__name__)


class CommandError(RuntimeError):
    """Raised when a subprocess returns a non-zero exit code."""

    def __init__(self, cmd: Sequence[str], returncode: int, stdout: str, stderr: str):
        self.cmd = list(cmd)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(
            f"command failed (rc={returncode}): {shlex.join(self.cmd)}\n"
            f"--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}"
        )


def run(
    cmd: Sequence[str],
    *,
    cwd: Path | str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = 300,
    check: bool = True,
    capture: bool = True,
    quiet: bool = False,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command and return CompletedProcess with text stdout/stderr.

    Defaults:
      - capture=True so stdout/stderr are available for assertions
      - check=True so non-zero exit raises CommandError
      - timeout=300s — bail loudly instead of hanging CI

    Override for streaming/long-running cases:
      - run([...], capture=False) lets the child inherit stdio
        (use this for `make test-e2e` where you want live progress)
    """
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)

    rendered = shlex.join(str(c) for c in cmd)
    if not quiet:
        logger.info("$ %s", rendered)

    started = time.monotonic()
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        env=merged_env,
        timeout=timeout,
        check=False,
        text=True,
        capture_output=capture,
        input=stdin,
    )
    elapsed = time.monotonic() - started

    if proc.returncode != 0 and check:
        raise CommandError(cmd, proc.returncode, proc.stdout or "", proc.stderr or "")

    if not quiet:
        logger.debug("  → rc=%d in %.1fs", proc.returncode, elapsed)
    return proc


def run_text(cmd: Sequence[str], **kwargs) -> str:
    """Convenience: run a command and return stripped stdout."""
    return run(cmd, **kwargs).stdout.strip()


def have(tool: str) -> bool:
    """True if the tool is on PATH."""
    return run(["which", tool], check=False, quiet=True).returncode == 0


def tool_version(tool: str, args: Sequence[str] = ("--version",)) -> str:
    """Return the first line of `tool --version` (best-effort, won't raise)."""
    try:
        out = run([tool, *args], check=False, quiet=True).stdout
        return out.splitlines()[0] if out else ""
    except (FileNotFoundError, CommandError):
        return ""
