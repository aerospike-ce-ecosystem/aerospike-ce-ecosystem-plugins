"""Session/function fixtures for ACKO e2e.

Layering:
  kind_cluster (session)
    └─ cert_manager_ready (session)
       └─ helm_release (session, default values)
          └─ live_cluster (session) — basic AerospikeCluster, phase=Completed
             └─ ui_api_url (function) — port-forward
                └─ api (function) — httpx client

Only `chart` tests skip cluster fixtures entirely. Everything else is
strictly ordered so the slow setup runs once.

Reuse policy:
  KEEP_CLUSTER=1 in env → don't tear down at session end (dev flow)
  Otherwise: cleanup.sh runs (helm uninstall + ns delete; Kind itself stays)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

# Make `helpers` and `scripts` reachable
_THIS = Path(__file__).resolve().parent
sys.path.insert(0, str(_THIS))

from helpers import env  # noqa: E402
from helpers.api_client import ApiClient  # noqa: E402
from helpers.cli import run  # noqa: E402
from helpers.port_forward import port_forward  # noqa: E402
from helpers.waits import wait_asc_completed  # noqa: E402

logger = logging.getLogger(__name__)
SCRIPTS = _THIS / "scripts"

# Stream D contract C-5 — Keycloak local realm.
# These match scripts/keycloak/acko-realm.json in the operator repo.
KEYCLOAK_REALM = "acko"
KEYCLOAK_CLIENT_ID = "acko-spa"
KEYCLOAK_OTHER_CLIENT_ID = "acko-other"
KEYCLOAK_AUDIENCE = "acko-api"
KEYCLOAK_USERS = {
    "admin": ("admin", "admin"),
    "dev": ("dev-user", "dev"),
    "prod": ("prod-user", "prod"),
}


# ---------------------------------------------------------------------------
# Marker shorthand
# ---------------------------------------------------------------------------
def pytest_configure(config: pytest.Config) -> None:
    # Markers are also declared in pyproject.toml; this is just for IDE hinting.
    pass


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Two adjustments to the default collection order:

    1. `heavy` is opt-in only — skip unless explicitly selected with `-m heavy`.
    2. All chart-only tests (`test_helm_lint`, `test_helm_matrix`, and
       `test_helm_real_install`) MUST run before any test that uses the
       `helm_release` session fixture. Otherwise the chart's CRD subchart is
       claimed by the long-lived `acko` release first, and the separate
       `acko-test` release tries to take ownership of the same CRDs and is
       refused with "annotation validation error: meta.helm.sh/release-name".
    """
    # 1. Heavy auto-skip — pytest registers `-m` under dest=`markexpr`
    selected = config.getoption("markexpr", default="") or ""
    if "heavy" not in selected:
        skip_heavy = pytest.mark.skip(reason="`heavy` lane is opt-in (use -m heavy)")
        for item in items:
            if "heavy" in item.keywords:
                item.add_marker(skip_heavy)

    # 2. Move helm_real_install (and chart-only tests) to the front so they
    #    run before the `helm_release` session fixture is created.
    pre, post = [], []
    for item in items:
        path = str(item.fspath)
        if "test_helm_real_install" in path or "test_helm_lint" in path or "test_helm_matrix" in path:
            pre.append(item)
        else:
            post.append(item)
    items[:] = pre + post


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run_script(name: str, *args: str, timeout: float = 600) -> None:
    path = SCRIPTS / name
    if not path.is_file():
        raise FileNotFoundError(f"missing script: {path}")
    cmd = ["bash", str(path), *args]
    logger.info("$ %s", " ".join(cmd))
    proc = subprocess.run(cmd, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"{name} failed (rc={proc.returncode})")


def _capture_diag_bundle() -> str | None:
    """Run diag-bundle.sh and return the bundle path, or None on error."""
    try:
        proc = subprocess.run(
            ["bash", str(SCRIPTS / "diag-bundle.sh")],
            timeout=120,
            check=False,
            capture_output=True,
            text=True,
        )
        # diag-bundle.sh echoes the bundle path on its last stdout line
        last = (proc.stdout or "").strip().splitlines()
        return last[-1] if last else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Session fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def operator_repo() -> Path:
    if not env.OPERATOR_REPO.is_dir():
        pytest.skip(f"OPERATOR_REPO not found at {env.OPERATOR_REPO}")
    return env.OPERATOR_REPO


@pytest.fixture(scope="session")
def chart_path(operator_repo: Path) -> Path:
    if not env.CHART_PATH.is_dir():
        pytest.skip(f"CHART_PATH not found at {env.CHART_PATH}")
    return env.CHART_PATH


@pytest.fixture(scope="session")
def kind_cluster(operator_repo: Path) -> Iterator[str]:
    """Bring up the Kind cluster + load the operator image. Reused across the session."""
    _run_script("kind-up.sh")
    yield env.KIND_CLUSTER
    if os.environ.get("KEEP_CLUSTER") == "1":
        logger.info("KEEP_CLUSTER=1 → leaving Kind cluster intact")
        return
    # Default: tear down namespaces but leave Kind cluster (so iterating tests is fast).
    # The dev opts in to deleting Kind explicitly via env var or by passing --kind to cleanup.sh.
    _run_script("cleanup.sh")


@pytest.fixture(scope="session")
def cert_manager_ready(kind_cluster: str) -> str:
    _run_script("cert-manager.sh")
    return env.CERT_MANAGER_VERSION


@pytest.fixture(scope="session")
def helm_release(cert_manager_ready: str) -> Iterator[dict]:
    """Default operator + UI install used by lifecycle/api/observability tests."""
    _run_script("helm-install.sh")
    yield {"release": env.HELM_RELEASE, "namespace": env.NS_OPERATOR}
    # Teardown happens in `kind_cluster`'s cleanup script — calling helm
    # uninstall here AND there would race during pytest's session shutdown.


@pytest.fixture(scope="session")
def live_cluster(helm_release: dict) -> Iterator[dict]:
    """Apply config/samples/acko_v1alpha1_aerospikecluster.yaml and wait Completed."""
    import yaml as _yaml

    sample = env.OPERATOR_REPO / "config" / "samples" / "acko_v1alpha1_aerospikecluster.yaml"
    if not sample.exists():
        pytest.skip(f"sample CR missing: {sample}")
    name = "aerospike-basic"
    ns = env.NS_AEROSPIKE

    # Ensure namespace (apply-with-dry-run pattern so re-runs don't error on "already exists")
    ns_yaml = run(
        ["kubectl", "create", "namespace", ns, "--dry-run=client", "-o", "yaml"],
        quiet=True,
    ).stdout
    run(["kubectl", "apply", "-f", "-"], stdin=ns_yaml, quiet=True)

    # Re-target sample to our namespace, in case the sample pins a different one.
    doc = _yaml.safe_load(sample.read_text())
    doc["metadata"]["name"] = name
    doc["metadata"]["namespace"] = ns
    run(["kubectl", "apply", "-f", "-"], stdin=_yaml.safe_dump(doc, sort_keys=False), quiet=True)

    wait_asc_completed(name, ns, timeout=300)
    yield {"name": name, "namespace": ns}

    # Best-effort delete; cleanup.sh nukes the whole ns at session end anyway.
    run(["kubectl", "delete", "asc", name, "-n", ns, "--ignore-not-found"], check=False)


# ---------------------------------------------------------------------------
# Function-scoped fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def ui_api_pf(helm_release: dict) -> Iterator[str]:
    """Open a port-forward to the ui-api Service; yield the http://localhost URL."""
    from helpers.cli import run_text

    svc = run_text(
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
    if not svc:
        pytest.skip("ui-api Service not found — is ui.api.enabled=true?")
    with port_forward(
        namespace=helm_release["namespace"],
        service=svc,
        local_port=18000,
        service_port=80,
    ) as url:
        yield url


@pytest.fixture
def api(ui_api_pf: str) -> Iterator[ApiClient]:
    with ApiClient(ui_api_pf) as client:
        yield client


# ---------------------------------------------------------------------------
# Keycloak fixtures (Stream D)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def keycloak_pf(kind_cluster: str) -> Iterator[str]:
    """Port-forward to the in-cluster Keycloak Service and yield the base URL.

    The local IdP is installed by `make run-local` / `make setup-test-e2e`
    using bitnami/keycloak with the acko realm imported. We assume it is
    already running — if it isn't, the fixture skips so unrelated lanes
    aren't punished.
    """
    # First check the namespace exists; if not, skip cleanly so chart-only
    # lanes that don't bring up Keycloak aren't forced to install it.
    chk = run(
        ["kubectl", "get", "ns", "keycloak", "--ignore-not-found", "-o", "name"],
        check=False,
        quiet=True,
    )
    if "namespace/keycloak" not in (chk.stdout or ""):
        pytest.skip(
            "Keycloak namespace not present — run `make run-local` or "
            "`make setup-test-e2e` first to install the local IdP"
        )

    # Wait for the deployment in case fixture order beat the install.
    run(
        [
            "kubectl",
            "wait",
            "--for=condition=Available",
            "deployment/keycloak",
            "-n",
            "keycloak",
            "--timeout=300s",
        ],
        check=False,
        quiet=True,
    )

    with port_forward(
        namespace="keycloak",
        service="keycloak",
        local_port=18080,
        service_port=80,
    ) as url:
        yield url


@pytest.fixture(scope="session")
def keycloak_url(keycloak_pf: str) -> str:
    """Base URL for the acko realm: e.g. http://localhost:18080/realms/acko."""
    explicit = os.environ.get("KEYCLOAK_URL")
    base = explicit.rstrip("/") if explicit else f"{keycloak_pf}/realms/{KEYCLOAK_REALM}"
    # Sanity-poll the well-known so the first test failure is informative.
    well_known = f"{base}/.well-known/openid-configuration"
    last_err: Exception | None = None
    for _ in range(30):
        try:
            r = httpx.get(well_known, timeout=3.0)
            if r.status_code == 200:
                return base
            last_err = RuntimeError(f"{well_known} returned {r.status_code}")
        except httpx.HTTPError as exc:
            last_err = exc
        import time as _time

        _time.sleep(2)
    raise RuntimeError(f"keycloak realm not ready at {well_known}: {last_err}")


@pytest.fixture(scope="session")
def keycloak_token(keycloak_url: str) -> Callable[..., str]:
    """Factory that fetches a fresh access token via Resource-Owner-Password-Credentials.

    Usage:
        token = keycloak_token(role="dev")            # dev-user
        token = keycloak_token(role="prod")           # prod-user
        token = keycloak_token(client_id="acko-other")  # negative-aud test
    """
    cache: dict[tuple[str, str], str] = {}

    def _token(
        role: str = "dev",
        client_id: str = KEYCLOAK_CLIENT_ID,
    ) -> str:
        if role not in KEYCLOAK_USERS:
            raise KeyError(f"unknown keycloak role {role!r}; one of {list(KEYCLOAK_USERS)}")
        username, password = KEYCLOAK_USERS[role]
        key = (client_id, username)
        if key in cache:
            return cache[key]
        token_url = f"{keycloak_url}/protocol/openid-connect/token"
        resp = httpx.post(
            token_url,
            data={
                "grant_type": "password",
                "client_id": client_id,
                "username": username,
                "password": password,
                "scope": "openid",
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"keycloak token endpoint {token_url} returned {resp.status_code}: {resp.text}"
            )
        access = resp.json().get("access_token")
        if not access:
            raise RuntimeError(f"keycloak token response missing access_token: {resp.text}")
        cache[key] = access
        return access

    return _token


# ---------------------------------------------------------------------------
# Failure → diag bundle
# ---------------------------------------------------------------------------
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if (
        rep.when == "call"
        and rep.failed
        and shutil.which("kubectl")
        and not getattr(item.session, "_acko_diag_done", False)
    ):
        bundle = _capture_diag_bundle()
        if bundle:
            rep.sections.append(("acko diag bundle", f"saved to {bundle}"))
        item.session._acko_diag_done = True
