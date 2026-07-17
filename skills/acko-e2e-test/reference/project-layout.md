# e2e_pytest project layout, reporting, and failure triage

## Project layout

```
e2e_pytest/
├── pyproject.toml         # uv project — pytest + httpx + pyyaml + tenacity
├── conftest.py            # session/function fixtures + heavy auto-skip + diag bundle hook
├── helpers/
│   ├── cli.py             # subprocess wrapper + CommandError
│   ├── env.py             # defaults (KIND_CLUSTER, IMG, NS_*, paths)
│   ├── api_client.py      # httpx wrapper for ui-api
│   ├── chart_yaml.py      # pyyaml-based chart manifest assertions
│   ├── otel_log.py        # collector debug-exporter log → typed Spans
│   ├── port_forward.py    # context manager
│   └── waits.py           # polling helpers (asc phase, asc gone)
├── scripts/               # CLI orchestration only — no assertion logic
│   ├── _common.sh         # shared defaults + log helpers
│   ├── kind-up.sh         # make setup-test-e2e + image build/load
│   ├── cert-manager.sh    # apply pinned cert-manager + wait
│   ├── helm-install.sh    # parametric (--otel, --log-format, --image, ...)
│   ├── load-image.sh      # podman save → kind load (collector, patched ui-api)
│   ├── cleanup.sh         # uninstall + delete ns (--kind also deletes Kind cluster)
│   └── diag-bundle.sh     # state + logs capture for failure post-mortem
└── tests/
    ├── chart/
    │   ├── test_helm_lint.py
    │   ├── test_helm_matrix.py        # 7 parametrized contracts
    │   └── test_helm_real_install.py
    ├── lifecycle/
    │   ├── test_asc_create_smoke.py   # 1-node CR happy path
    │   └── test_ginkgo.py             # subprocess go test wrapper
    ├── api/
    │   ├── test_api_crud.py           # A–G (#257-#260 regression guards)
    │   └── test_api_k8s_create.py     # /api/v1/k8s/clusters CRUD
    └── observability/
        ├── test_logging.py            # text/json + X-Request-ID
        └── test_otel_runtime.py       # collector + correlated spans (#265 guard)
```

The split is principled: bash where the contract is "this CLI invocation succeeds" (kind/cert-manager/helm install/cleanup), Python where the contract is "this response/manifest/log shape matches" (chart YAML, httpx responses, OTel spans).

## Reporting

`uv run pytest` produces standard pytest output. For richer reports:

```bash
uv run pytest -m smoke --html=/tmp/e2e-report.html --self-contained-html
```

On failure, `conftest.py`'s `pytest_runtest_makereport` hook automatically calls `scripts/diag-bundle.sh`. The path to the bundle (`/tmp/e2e-diag-<timestamp>/`) appears in the failed test's report sections so it shows up in `--html` output and CI logs.

## Common failures — first-look table

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `kind create cluster` hangs on macOS | Podman machine not running | `podman machine start && podman system service --time=0 &` |
| Operator pod `ImagePullBackOff` for `controller:latest` | Image not loaded into Kind | re-run `bash scripts/kind-up.sh` |
| `phase=Error` on first reconcile, no useful logs | Webhook rejected CR (server-side apply ate the message) | `kubectl get events -n <ns>` — webhook errors land there as Warning |
| `phase=BackoffActive` (not Error, not Completed) | Reconciliation Circuit Breaker tripped | inspect `.status.conditions[?(@.type=="ReconcileHealthy")]`; reset by editing the CR or toggling `paused: true → null` |
| `helm template` fails for `ingress.target=web` + `web.enabled=false` | Chart's intentional failfast (since #236) | set `ui.ingress.target=api` or enable web |
| e2e passes locally, fails in CI | Different `CONTAINER_TOOL` (Docker vs Podman) | confirm CI sets `CONTAINER_TOOL=podman KIND_PROVIDER=podman` |
| Collector image `0.115.0` not found on docker.io | Tag rotated out of registry | `tests/observability/test_otel_runtime.py` auto-falls back to `$COLLECTOR_IMAGE` (defaults to `:latest`) and reloads |
| OTel env wired but no spans at collector | `FastAPIInstrumentor` regression | `test_otel_runtime_emits_correlated_traces` fails with "no opentelemetry.instrumentation.fastapi scope" — re-apply cluster-manager #265 |
