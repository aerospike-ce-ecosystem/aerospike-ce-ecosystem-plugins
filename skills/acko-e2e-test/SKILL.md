---
name: acko-e2e-test
description: "MUST USE for ACKO end-to-end testing on Kind/local clusters. Contains the canonical scenario list (deploy, scale, rolling update, multi-rack, ACL, PVC, Helm chart split-mode, OTel observability, UI api CRUD), Ginkgo label conventions (`heavy` vs default), the project's mandatory `helm install`-based operator setup (NOT `make run-local`/`make deploy` — those bypass the real user install path), and performance-check procedures the project expects every release to verify. Each contract maps to a pytest test under `e2e_pytest/tests/` (Python for assertions/parsing/httpx, bash scripts under `e2e_pytest/scripts/` for CLI orchestration). Without this skill, e2e runs miss scenarios that have caught regressions historically and may install the operator via paths real users never take. Triggers on: ACKO e2e test, kind cluster test, make test-e2e, release verification, performance test for Aerospike operator, helm chart test, post-merge smoke test, regression checklist, regression guard tests, Ginkgo label heavy, pytest e2e_pytest scenario, e2e test failure debugging."
---

# ACKO End-to-End Test Playbook

This skill encodes **what counts as PASS** for each ACKO release-verification concern, plus a `e2e_pytest/` project that **performs and asserts** each contract.

The skill is opinionated about three things:

1. **Real users install via Helm.** e2e MUST exercise `helm install ./charts/...`. `make run-local` and `make deploy` are forbidden — they bypass the chart and miss regressions in RBAC, CRD bundling, value defaults, helper templates.
2. **Eval criteria live here, mechanics live in tests.** This file does NOT contain bash blobs or kubectl commands. If you find yourself typing `kubectl ...` while reading this, stop — the test in `e2e_pytest/tests/` is the source of truth.
3. **Two-language hybrid.** Python (pytest + httpx + pyyaml) for assertion-heavy work; bash (`scripts/`) for the CLI orchestration chain (kind up, helm install, cleanup).

---

## Bootstrap (fresh box — Ubuntu / macOS / Codespaces / Claude Code env)

Needs: `uv`, `kind`, `podman`, `kubectl`, `helm`, `go`, `jq` plus a local clone of `aerospike-ce-kubernetes-operator`. One-shot installer:

```bash
cd skills/acko-e2e-test/e2e_pytest
bash scripts/bootstrap.sh                 # install everything missing (apt or brew)
bash scripts/bootstrap.sh --check         # status only — install nothing
bash scripts/bootstrap.sh --no-operator   # don't auto-clone the operator repo
```

The operator repo is discovered automatically — `helpers/env.py` tries (in order): `$OPERATOR_REPO`, the workspace-sibling layout, `$CWD/aerospike-ce-kubernetes-operator`, `~/aerospike-ce-kubernetes-operator`, `~/github/aerospike-ce-kubernetes-operator`, `/workspace/aerospike-ce-kubernetes-operator`. If none exist, fixtures `pytest.skip()` with a clear message.

## How to run

```bash
cd skills/acko-e2e-test/e2e_pytest
uv sync                          # one-time: pull pytest + httpx + pyyaml + tenacity

uv run pytest -m chart           # fast gate — chart-template only, no Kind (~5s)
uv run pytest -m smoke           # chart + cluster + api + observability (~10 min)
uv run pytest -m "smoke or full" # + the in-tree Ginkgo go test (~30+ min)
uv run pytest -m heavy           # opt-in lane, never auto-selected
```

`KEEP_CLUSTER=1 uv run pytest -m smoke` keeps the Kind cluster for iterative debugging. Override env defaults in `helpers/env.py` (KIND_CLUSTER, IMG, NS_*, paths) or via env vars (e.g. `OPERATOR_REPO=/path/to/repo`).

## Run modes (pytest markers)

| Marker | When to use | Time | Cluster needed |
|--------|-------------|------|-----------------|
| `chart` | Chart-only PR | ~5s | no |
| `smoke` | Most PRs (functional + api + observability) | ~10 min | yes |
| `full` | Pre-release / post-rebase / weekly main | ~30+ min | yes |
| `heavy` | Soak / large-cluster lane | varies | yes |
| `regression_guard` | Bug-specific re-asserts (#257, #258, #259, #260, #265, #235, #236) | (composes with above) | varies |

The `heavy` lane is opt-in — `conftest.py` skips heavy tests unless `-m heavy` is passed explicitly (matches Ginkgo's heavy-label semantics). `heavy` Ginkgo label scope: `e2e_multirack_test.go`, `e2e_pvc_test.go`, `e2e_template_test.go` are heavy at suite level; `e2e_cluster_test.go` and `e2e_features_test.go` mark specific Contexts heavy. Confirm against the test file before reasoning about scope.

## Eval criteria — index

Full PASS contracts (per-test assertions, chart matrix table, API CRUD checks A–G, logging/OTel specifics, perf budgets): **[`./reference/eval-criteria.md`](./reference/eval-criteria.md)**.

| Concern | Owning test(s) | PASS in one line |
|---------|----------------|------------------|
| Cluster lifecycle | `tests/lifecycle/test_asc_create_smoke.py`, `test_ginkgo.py` | sample CR reaches `Completed` <5min with all resources; Ginkgo suite 100% |
| Webhook / CE constraints | in-tree Ginkgo suite | every CE constraint rejected at admission (size>8, ns>2, xdr/tls, enterprise image, ACL scopes, per-rack config, …) |
| Helm chart matrix | `tests/chart/test_helm_matrix.py`, `test_helm_lint.py` | 8 toggle combinations render exactly the right resources; lint clean |
| Helm real install | `tests/chart/test_helm_real_install.py` | `helm install` + `helm test` succeed on a fresh namespace; uninstall leaves nothing |
| UI api CRUD | `tests/api/test_api_crud.py` | connection/sample-data/records/query/indexes contracts A–G, incl. #257–#260 regression guards |
| UI api K8s management | `tests/api/test_api_k8s_create.py` | CR create→Completed→get/health/yaml→delete via `/api/v1/k8s/clusters` |
| Logging | `tests/observability/test_logging.py` | text/JSON switch + X-Request-ID round-trip correlation |
| OTel | `tests/observability/test_otel_runtime.py` | opt-in env wiring + correlated FastAPI→asyncpg spans at a real collector (#265 guard); operator-side export verified incl. NetworkPolicy egress |
| Performance / soak | release-tag only (TODOs) | budgets in `reference/eval-criteria.md`; record results in project-hub release notes |

## Project layout, reporting, failure triage

See **[`./reference/project-layout.md`](./reference/project-layout.md)** for the `e2e_pytest/` tree (helpers vs scripts vs tests), HTML reporting + automatic diag-bundle capture, and the common-failures first-look table (podman machine, ImagePullBackOff, webhook-eaten errors, `BackoffActive`, CI container-tool drift, collector image fallback, FastAPIInstrumentor regression). Manual one-off commands (Kind lifecycle, single Ginkgo scenario, hand-driven Helm install path): **[`./reference/quick-commands.md`](./reference/quick-commands.md)**.

## When to update

- A new `Context(...)` lands in `test/e2e/` (the operator's Ginkgo) → no change here; `tests/lifecycle/test_ginkgo.py` runs the whole suite. If it tests a brand-new concern (e.g. backup), add a row above, the full contract in `reference/eval-criteria.md`, and a new `tests/<area>/test_<thing>.py`.
- A new chart toggle is introduced → add a parametrize entry to `tests/chart/test_helm_matrix.py` and a matrix row in `reference/eval-criteria.md`.
- A regression caught in production → add a `regression_guard`-marked test that re-asserts the contract. Don't grow the markdown.
- A perf budget renegotiated → record both old and new values in `reference/eval-criteria.md`.

The skill version is implicit in `git log` — don't bump anything in this file.
