"""Helm chart manifest parsing — `helm template` → list[dict] → assertions.

This is where Python pulls its weight over the bash version: dict access
beats `yq` pipelines, and pytest assertion introspection shows the actual
manifest fields when something fails.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from .cli import run, run_text


def lint(chart: Path | str) -> str:
    return run_text(["helm", "lint", str(chart)])


def template(
    chart: Path | str,
    sets: Mapping[str, str],
    *,
    release_name: str = "foo",
) -> list[dict]:
    """Render the chart and return parsed YAML manifests (None entries dropped)."""
    cmd = ["helm", "template", release_name, str(chart)]
    for k, v in sets.items():
        cmd += ["--set", f"{k}={v}"]
    out = run_text(cmd)
    return [doc for doc in yaml.safe_load_all(out) if doc]


def template_expect_fail(chart: Path | str, sets: Mapping[str, str]) -> str:
    """Run `helm template`; raise if it succeeds; otherwise return the error."""
    cmd = ["helm", "template", "foo", str(chart)]
    for k, v in sets.items():
        cmd += ["--set", f"{k}={v}"]
    proc = run(cmd, check=False)
    if proc.returncode == 0:
        raise AssertionError(f"helm template was expected to fail but succeeded:\n{proc.stdout}")
    return (proc.stderr or proc.stdout or "").strip()


# ---------------------------------------------------------------------------
# Manifest dict accessors — the chart-matrix tests use these
# instead of yq+awk pipelines.
# ---------------------------------------------------------------------------
def find_kind(docs: Iterable[dict], kind: str) -> list[dict]:
    return [d for d in docs if d.get("kind") == kind]


def find_named(docs: Iterable[dict], kind: str, name: str) -> dict | None:
    for d in docs:
        if d.get("kind") == kind and d.get("metadata", {}).get("name") == name:
            return d
    return None


def deployment_names(docs: Iterable[dict]) -> list[str]:
    return [d["metadata"]["name"] for d in docs if d.get("kind") == "Deployment"]


def service_names(docs: Iterable[dict]) -> list[str]:
    return [d["metadata"]["name"] for d in docs if d.get("kind") == "Service"]


def helm_test_pods(docs: Iterable[dict]) -> list[dict]:
    """Pods carrying the `helm.sh/hook: test` annotation."""
    out = []
    for d in docs:
        if d.get("kind") != "Pod":
            continue
        anns = (d.get("metadata") or {}).get("annotations") or {}
        if anns.get("helm.sh/hook") == "test":
            out.append(d)
    return out


def container_env(deploy: dict, container_name: str) -> dict[str, str | None]:
    for c in deploy["spec"]["template"]["spec"].get("containers", []) or []:
        if c.get("name") == container_name:
            return {e["name"]: e.get("value") for e in (c.get("env") or [])}
    raise KeyError(f"container {container_name!r} not found in deploy {deploy['metadata']['name']!r}")


def network_policy_ports(np: dict) -> set[int]:
    out: set[int] = set()
    for rule in np.get("spec", {}).get("ingress", []) or []:
        for p in rule.get("ports", []) or []:
            port = p.get("port")
            if isinstance(port, int):
                out.add(port)
    return out
