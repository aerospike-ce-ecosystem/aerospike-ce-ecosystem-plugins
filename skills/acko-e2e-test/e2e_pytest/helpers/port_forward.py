"""Port-forward as a context manager.

Why not just `kubectl port-forward &` in a fixture: cleanup is brittle —
killed PIDs go zombie when pytest crashes. The context manager owns the
Popen handle and terminates it cleanly on exit (success or exception).
"""

from __future__ import annotations

import contextlib
import logging
import shlex
import socket
import subprocess
import time
from collections.abc import Iterator

logger = logging.getLogger(__name__)


def _is_listening(host: str, port: int, *, timeout: float = 0.3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@contextlib.contextmanager
def port_forward(
    *,
    namespace: str,
    service: str,
    local_port: int,
    service_port: int,
    timeout: float = 15.0,
) -> Iterator[str]:
    """Open `kubectl port-forward` and yield the http://localhost:<port> URL.

    Waits up to `timeout` for the local port to start accepting TCP, so the
    caller's first request doesn't race the forward.
    """
    cmd = [
        "kubectl",
        "port-forward",
        "-n",
        namespace,
        f"svc/{service}",
        f"{local_port}:{service_port}",
    ]
    logger.info("$ %s", shlex.join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err = proc.stderr.read() if proc.stderr else ""
                raise RuntimeError(f"port-forward exited early (rc={proc.returncode}): {err}")
            if _is_listening("localhost", local_port):
                break
            time.sleep(0.2)
        else:
            raise TimeoutError(f"port-forward to svc/{service}:{service_port} did not become ready")

        yield f"http://localhost:{local_port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
