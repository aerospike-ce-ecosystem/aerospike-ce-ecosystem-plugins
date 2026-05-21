---
name: acko-e2e-test
description: "MUST USE for ACKO end-to-end testing on Kind/local clusters. Contains the canonical scenario list (deploy, scale, rolling update, multi-rack, ACL, PVC, Helm chart split-mode, OTel observability, UI api CRUD), Ginkgo label conventions (`heavy` vs default), the project's mandatory `helm install`-based operator setup (NOT `make run-local`/`make deploy` — those bypass the real user install path), and performance-check procedures the project expects every release to verify. Each contract maps to a pytest test under `e2e_pytest/tests/` (Python for assertions/parsing/httpx, bash scripts under `e2e_pytest/scripts/` for CLI orchestration). Without this skill, e2e runs miss scenarios that have caught regressions historically (CE 8.1 data-size rename, webhook duplicate ServiceMonitor, helm test pod in web-only mode, circuit-breaker BackoffActive, missing FastAPIInstrumentor in OTel pipeline #265) and they may install the operator via paths real users never take. Triggers on: ACKO e2e test, kind cluster test, make test-e2e, release verification, performance test for Aerospike operator, helm chart test, post-merge smoke test, regression checklist."
---

# ACKO End-to-End Test Playbook

This skill encodes **what counts as PASS** for each ACKO release-verification concern in natural language, plus a `e2e_pytest/` project that **performs and asserts** each contract.

The skill is opinionated about three things:

1. **Real users install via Helm.** e2e MUST exercise `helm install ./charts/...`. `make run-local` and `make deploy` are forbidden — they bypass the chart and miss regressions in RBAC, CRD bundling, value defaults, helper templates.
2. **Eval criteria live here, mechanics live in tests.** This file does NOT contain bash blobs or kubectl commands. If you find yourself typing `kubectl ...` while reading this, stop — the test in `e2e_pytest/tests/` is the source of truth.
3. **Two-language hybrid.** Python (pytest + httpx + pyyaml) for assertion-heavy work where introspection and dict access pull their weight. Bash (`scripts/`) for the CLI orchestration chain (kind up, helm install, cleanup) where wrapping `kubectl` in Python is just pure overhead.

---

## Bootstrap (fresh box — Ubuntu / macOS / Codespaces / Claude Code env)

The skill needs: `uv`, `kind`, `podman`, `kubectl`, `helm`, `go`, `jq` plus a local clone of `aerospike-ce-kubernetes-operator`. There's a one-shot installer that detects what's missing and installs only that:

```bash
cd skills/acko-e2e-test/e2e_pytest
bash scripts/bootstrap.sh           # install everything missing (uses apt or brew)
bash scripts/bootstrap.sh --check   # status only — install nothing
bash scripts/bootstrap.sh --no-operator   # don't auto-clone the operator repo
```

The operator repo is discovered automatically — `helpers/env.py` tries (in order): `$OPERATOR_REPO`, the workspace-sibling layout (`<workspace>/aerospike-ce-kubernetes-operator`), `$CWD/aerospike-ce-kubernetes-operator`, `~/aerospike-ce-kubernetes-operator`, `~/github/aerospike-ce-kubernetes-operator`, `/workspace/aerospike-ce-kubernetes-operator`. If none exist, fixtures `pytest.skip()` with a clear message — no hard import-time failure.

## How to run

```bash
cd skills/acko-e2e-test/e2e_pytest
uv sync                          # one-time: pull pytest + httpx + pyyaml + tenacity

# Fast gate — chart-template only, no Kind cluster (~5s)
uv run pytest -m chart

# Smoke — chart + cluster + api + observability (~10 min)
uv run pytest -m smoke

# Full — smoke + the in-tree Ginkgo go test (~30+ min)
uv run pytest -m "smoke or full"

# Heavy — opt-in lane, never auto-selected
uv run pytest -m heavy
```

`KEEP_CLUSTER=1 uv run pytest -m smoke` keeps the Kind cluster after teardown for iterative debugging. Override env defaults in `helpers/env.py` (KIND_CLUSTER, IMG, NS_*, paths) or via env vars (e.g. `OPERATOR_REPO=/path/to/repo`) when running outside the assumed layout.

---

## Run modes (pytest markers)

| Marker | When to use | Time | Cluster needed |
|--------|-------------|------|-----------------|
| `chart` | Chart-only PR | ~5s | no |
| `smoke` | Most PRs (functional + api + observability) | ~10 min | yes |
| `full` | Pre-release / post-rebase / weekly main | ~30+ min | yes |
| `heavy` | Soak / large-cluster lane | varies | yes |
| `regression_guard` | Bug-specific re-asserts (#257, #258, #259, #260, #265, #235, #236) | (composes with above) | varies |

The `heavy` lane is opt-in — `conftest.py` skips heavy tests unless the user explicitly passes `-m heavy`. This matches Ginkgo's heavy-label semantics and prevents an inadvertent 30-min run from a no-arg `pytest`.

`heavy` Ginkgo label scope: `e2e_multirack_test.go`, `e2e_pvc_test.go`, and `e2e_template_test.go` are heavy at suite level; `e2e_cluster_test.go` and `e2e_features_test.go` mark specific Contexts heavy. Confirm against the test file before reasoning about scope.

---

## Eval criteria (what counts as PASS)

Every section below is owned by one or more pytest tests. The pytest test file is the contract — read it before changing it.

### Functional — operator + cluster lifecycle

The operator reconciles AerospikeCluster CRs through every supported lifecycle event without losing data, leaking PVCs, or leaving the CR in a non-terminal phase.

PASS when:

- **`tests/lifecycle/test_asc_create_smoke.py`** — applying `config/samples/acko_v1alpha1_aerospikecluster.yaml` results in `phase=Completed` within 5 min, the expected K8s resources exist (StatefulSet, headless Service, ConfigMap, PDB), `status.size == spec.size`, and `status.pods` reports the right number of running+ready entries. Deleting the CR removes the namespace's ASC count to 0; re-applying it returns to Completed.
- **`tests/lifecycle/test_ginkgo.py`** — the in-tree Ginkgo suite (`go test ./test/e2e/`) passes 100% with no `FAIL!` lines. Covers single-node + 3-node PVC + multi-rack 6-node + ACL/cascadeDelete + PVC create/retain/cleanup + multi-rack scale + custom metrics + perPodStatus configHash + rolling restart + scale up/down + RollingUpdateBatchSize + paused cluster + PDB enable/disable + template + drift detection. Mode selectable via `GINKGO_MODE` env var.

### Functional — webhook validation (CE constraints)

Every CE constraint is enforced at admission so users cannot accidentally configure an enterprise feature.

PASS when (currently asserted via the in-tree Ginkgo suite, scheduled for split into `tests/lifecycle/test_webhook.py`):

- `size > 8` is rejected
- `namespaces > 2` is rejected
- `network.tls`, `xdr`, enterprise images (`aerospike-server-enterprise`), `feature-key-file` are rejected
- A duplicate `ServiceMonitor` when `monitoring.enabled=true` is rejected (#235)

### Helm chart — manifest matrix

The chart renders correctly across every supported toggle combination and fails fast on incompatible ones.

PASS when **`tests/chart/test_helm_matrix.py`** verifies the matrix:

| Mode | Contract |
|------|----------|
| **operator-only** (`--set ui.enabled=false`) | Operator Deployment present; NO ui-api/ui-web; NO ServiceMonitor |
| **UI full** (api + web) | api + web Deployments; NetworkPolicy with both `:8000` and `:3100`; helm-test pod present |
| **UI api-only** | api only; NetworkPolicy with ONLY `:8000`; helm-test pod present |
| **UI web-only** | web only; NetworkPolicy with ONLY `:3100`; web pod has `automountServiceAccountToken=false`; NO helm-test pod |
| **OTel disabled (default)** | `OTEL_SDK_DISABLED=true` in api env; no OTLP endpoint |
| **OTel enabled** | `OTEL_SDK_DISABLED=false`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_SAMPLER`, `OTEL_SERVICE_NAME` all set |
| **`ingress.target` failfast** | `helm template` MUST fail with an error mentioning `ui.ingress.target` |

Plus **`tests/chart/test_helm_lint.py`** — `helm lint` reports no `[ERROR]` entries.

> ⚠️ **Drift note**: The chart's current default is `ui.enabled=true`. The "operator-only" row uses `--set ui.enabled=false` explicitly. If the default flips, update the parametrize entry.

### Helm chart — real install + helm test

`helm template` catches static regressions but misses things that only surface during apply (CRD ordering, hook race, RBAC propagation, hanging helm-test pods like #236).

PASS when **`tests/chart/test_helm_real_install.py`**:

- `helm install` on a fresh namespace succeeds and pods reach Running
- `helm test <release>` reports `Phase: Succeeded`
- `helm uninstall` + namespace deletion leaves no leftover state

### UI api — CRUD smokes

The cluster-manager api is the user-facing surface for record browsing, query, sample data, and indexes. Several router-level regressions historically returned 500 instead of well-formed responses (#257–#260) — these are re-asserted on every run as `regression_guard` tests.

PASS when **`tests/api/test_api_crud.py`** verifies all of:

- **A. Connection lifecycle** — `POST /api/v1/connections` returns 201 + `id` + `createdAt`; `GET` list contains it; `DELETE` returns 204; subsequent `GET` returns 404.
- **B. Cluster reachability** — `GET /api/v1/clusters/{conn_id}` returns 200 with `namespaces[].name` including `test`. Confirms aerospike-py wiring inside the api pod.
- **C. sample-data partial-success** (#257) — `POST /api/v1/sample-data/{conn_id}` returns 201 with `recordsCreated`, `recordsFailed`, `indexesCreated`, `indexesFailed` keys. **Critical**: NEVER 500 even when some indexes fail.
- **D. records empty/sparse namespace** (#259) — `GET /api/v1/records/{conn_id}?ns=test&set=does-not-exist` returns 200 with `records:[]` (NOT 500).
- **E. query `pkType=auto`** (#258) — `POST /api/v1/query/{conn_id}` with `{"pkType":"auto"}` returns 200, identical behavior to omitting `pkType`.
- **F. indexes idempotency** (#260) — `POST` returns 201 with `state: building|ready`; `DELETE` returns 204; calling `DELETE` again on the same name still returns 204 (no orphaned 500).
- **G. X-Request-ID round-trip** — every response carries `x-request-id` echoing whatever the caller sent.

### UI api — K8s management create/delete

Real UI users create AerospikeCluster CRs through the api, not directly with `kubectl`. The whole `/api/v1/k8s/clusters/...` family was previously untested in e2e.

PASS when **`tests/api/test_api_k8s_create.py`**:

- `POST /api/v1/k8s/clusters` creates a 1-node CR via the api → 200/201/202
- The CR appears in `kubectl get asc` and reaches `phase=Completed`
- `GET .../{ns}/{name}` returns 200 with the right `metadata.name`
- `GET .../health` returns 200
- `GET .../yaml` returns parseable YAML
- `DELETE .../{ns}/{name}` removes the CR; subsequent `GET` returns 404

### Logging — text vs JSON, request correlation

PASS when **`tests/observability/test_logging.py`**:

- Default `LOG_FORMAT=text` produces `YYYY-... INFO [logger] message` lines
- `helm upgrade --set ui.env.logFormat=json` switches every record to a JSON object with `timestamp`, `level`, `logger`, `message`, `request_id` keys
- A `curl -H "X-Request-ID: <id>"` request echoes the id in `x-request-id` response header AND embeds it as `request_id` in the matching JSON log record. Caller can correlate without server access.
- Note: the middleware-emitted access log line shows `trace_id: null, span_id: null` even when OTel is fully enabled — this is by design (the middleware writes after the OTel span closes). Logs emitted from inside route handlers carry the real trace IDs.

### OTel — opt-in env wiring + runtime export

PASS when **`tests/observability/test_otel_runtime.py`** (regression_guard for cluster-manager #265):

- `helm upgrade --set ui.api.otel.enabled=true,...endpoint=...` flips `OTEL_SDK_DISABLED=false` and sets `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_TRACES_SAMPLER`, `OTEL_SERVICE_NAME=aerospike-cluster-manager-api`.
- A deployed OpenTelemetry collector (`reference/otel-collector.yaml`) receives traces with `service.name: aerospike-cluster-manager-api`.
- **Both** `opentelemetry.instrumentation.fastapi` and `opentelemetry.instrumentation.asyncpg` instrumentation scopes appear at the collector. Before #265 only asyncpg spans showed up, parent-less.
- At least one trace contains a Server-kind FastAPI span (HTTP request) **and** an asyncpg child span sharing the same trace ID — proving HTTP→DB context propagation.

### Performance / soak (release-tag only)

These are **not** gated on every PR but are required before tagging a minor release. Currently captured as TODOs; record results in `project-hub/docs/docs/history/releases/<version>/perf.md`.

PASS targets:

- **Reconcile loop** — 6-node multi-rack, 10× no-op `kubectl edit` → p99 reconcile < 2 s, circuit breaker stays Closed.
- **Rolling restart** — 8-node + `RollingUpdateBatchSize=2` → restart in `(size/batchSize) × (warm_restart + 30s)`, no `BackoffActive`.
- **Scale-up burst** — 1 → 8 nodes in one patch → all Ready < 5 min on Kind, no PVC stuck.
- **Webhook latency** — `kubectl apply` 100 invalid CRs in a tight loop → 100% rejected, no API server timeout, operator stays Ready.
- **Memory ceiling** — 1h soak under 6-node multi-rack → operator RSS < 256 MiB, no OOM, no fd leak.
- **OTel egress when disabled** — default install + `tcpdump :4317,4318` for 10 min → 0 packets.

---

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

---

## Reporting

`uv run pytest` produces standard pytest output. For richer reports:

```bash
uv run pytest -m smoke --html=/tmp/e2e-report.html --self-contained-html
```

On failure, `conftest.py`'s `pytest_runtest_makereport` hook automatically calls `scripts/diag-bundle.sh`. The path to the bundle (`/tmp/e2e-diag-<timestamp>/`) appears in the failed test's report sections so it shows up in `--html` output and CI logs.

---

## Common failures — first-look table

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `kind create cluster` hangs on macOS | Podman machine not running | `podman machine start && podman system service --time=0 &` |
| Operator pod `ImagePullBackOff` for `controller:latest` | Image not loaded into Kind | re-run `bash scripts/kind-up.sh` |
| `phase=Error` on first reconcile, no useful logs | Webhook rejected CR (server-side apply ate the message) | `kubectl get events -n <ns>` — webhook errors land there as Warning |
| `phase=BackoffActive` (not Error, not Completed) | Reconciliation Circuit Breaker tripped | inspect `.status.conditions[?(@.type=="ReconcileBackoff")]`; reset by editing the CR or restarting operator |
| `helm template` fails for `ingress.target=web` + `web.enabled=false` | Chart's intentional failfast (since #236) | set `ui.ingress.target=api` or enable web |
| e2e passes locally, fails in CI | Different `CONTAINER_TOOL` (Docker vs Podman) | confirm CI sets `CONTAINER_TOOL=podman KIND_PROVIDER=podman` |
| Collector image `0.115.0` not found on docker.io | Tag rotated out of registry | `tests/observability/test_otel_runtime.py` auto-falls back to `$COLLECTOR_IMAGE` (defaults to `:latest`) and reloads |
| OTel env wired but no spans at collector | `FastAPIInstrumentor` regression | `test_otel_runtime_emits_correlated_traces` fails with "no opentelemetry.instrumentation.fastapi scope" — re-apply cluster-manager #265 |

---

## When to update

- A new `Context(...)` lands in `test/e2e/` (the operator's Ginkgo) → no change here; `tests/lifecycle/test_ginkgo.py` runs the whole suite. If it tests a brand-new concern (e.g. backup), add a section above and a new `tests/<area>/test_<thing>.py`.
- A new chart toggle is introduced (e.g. `ui.postgresql.external`) → add a new parametrize entry to `tests/chart/test_helm_matrix.py`.
- A regression caught in production → add a `regression_guard`-marked test that re-asserts the contract. Don't grow the markdown.
- A perf budget renegotiated → record both old and new values in the perf section.

The skill version is implicit in `git log` — don't bump anything in this file.
