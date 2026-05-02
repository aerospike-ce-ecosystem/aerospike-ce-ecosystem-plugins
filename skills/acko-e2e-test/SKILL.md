---
name: acko-e2e-test
description: "MUST USE for ACKO end-to-end testing on Kind/local clusters. Contains the canonical scenario list (deploy, scale, rolling update, multi-rack, ACL, PVC, Helm chart split-mode, OTel observability, UI api CRUD), Ginkgo label conventions (`heavy` vs default), the project's mandatory `helm install`-based operator setup (NOT `make run-local`/`make deploy` — those bypass the real user install path), and performance-check procedures the project expects every release to verify. Each section ships an executable script under `scripts/` that the orchestrator (`scripts/run-all.sh`) sequences. Without this skill, e2e runs miss scenarios that have caught regressions historically (CE 8.1 data-size rename, webhook duplicate ServiceMonitor, helm test pod in web-only mode, circuit-breaker BackoffActive, missing FastAPIInstrumentor in OTel pipeline #265) and they may install the operator via paths real users never take. Triggers on: ACKO e2e test, kind cluster test, make test-e2e, release verification, performance test for Aerospike operator, helm chart test, post-merge smoke test, regression checklist."
---

# ACKO End-to-End Test Playbook

This skill encodes **what counts as PASS** for each ACKO release-verification concern in natural language, plus a `scripts/` directory that **performs and asserts** each contract. Use it when validating an ACKO PR, a chart change, or a cluster-manager image bump.

The skill is opinionated about two things:

1. **Real users install via Helm.** e2e MUST exercise `helm install ./charts/...`. `make run-local` and `make deploy` are forbidden — they bypass the chart and miss regressions in RBAC, CRD bundling, value defaults, helper templates.
2. **Eval criteria live here, mechanics live in scripts.** This file does NOT contain bash blobs. If you find yourself typing `kubectl ...` while reading this, stop — the script in `scripts/` is the source of truth.

---

## How to run

```bash
# from the skill directory:
./scripts/run-all.sh --mode chart       # PR-time fast gate (~1 min, no cluster)
./scripts/run-all.sh --mode smoke       # smoke incl. cluster + api + OTel (~10 min)
./scripts/run-all.sh --mode full        # smoke + full Ginkgo suite (~30–45 min)
./scripts/run-all.sh --mode ginkgo --ginkgo-mode heavy   # heavy-only Ginkgo
```

The orchestrator parses every script's last line (the `e2e:pass[scope=...]` / `e2e:fail[scope=...]` contract) and emits the standard report described in [§ Reporting](#reporting). Each step's full output is at `/tmp/run-all-<step>.out`. On failure, a diagnostic bundle lands at `/tmp/e2e-diag-<timestamp>/`.

Override env vars to customize: `KIND_CLUSTER`, `IMG`, `API_IMG`, `NS_OPERATOR`, `NS_AEROSPIKE`, `HELM_RELEASE`. See `scripts/lib.sh` for the full list.

---

## Run modes

| Mode | When to use | Time | Steps |
|------|-------------|------|-------|
| `chart` | Chart-only PR; no controller change | ~1 min | 40 |
| `smoke` | Most PRs (functional + api + OTel, no Ginkgo) | ~10 min | 40 → 41 → 10 → 11 → 12 → 21 → 30 → 33 → 31 → 32 → 99 |
| `full` | Pre-release / post-rebase / weekly main | ~30–45 min | smoke + 20 (Ginkgo full) |
| `ginkgo` | Iterating on a specific scenario | varies | 10 → 20 (focus or label-filter) |

`heavy` Ginkgo label scope: `e2e_multirack_test.go`, `e2e_pvc_test.go`, and `e2e_template_test.go` are heavy at suite level; `e2e_cluster_test.go` and `e2e_features_test.go` mark specific Contexts heavy. Confirm against the test file before reasoning about scope.

---

## Eval criteria (what counts as PASS)

Every section maps 1:1 to a script. The script's last-line contract `e2e:pass[scope=<X>]` is what tools (or humans) grep for to decide green/red.

### Functional — operator + cluster lifecycle

The operator reconciles AerospikeCluster CRs through every supported lifecycle event without losing data, leaking PVCs, or leaving the CR in a non-terminal phase.

PASS when:

- **`scripts/21-asc-create-smoke.sh`** — applying `config/samples/acko_v1alpha1_aerospikecluster.yaml` results in `phase=Completed` within 3 min, the expected K8s resources exist (StatefulSet, headless Service, ConfigMap, PDB), `status.size == spec.size`, and `status.pods` reports the right number of running+ready entries. Deleting the CR removes the namespace's ASC count to 0.
- **`scripts/20-ginkgo.sh`** — the in-tree Ginkgo suite (`test/e2e/`) passes 100% with no FAIL lines. Covers single-node + 3-node PVC + multi-rack 6-node + ACL/cascadeDelete + PVC create/retain/cleanup + multi-rack scale + custom metrics + perPodStatus configHash + rolling restart + scale up/down + RollingUpdateBatchSize + paused cluster + PDB enable/disable + template + drift detection.

### Functional — webhook validation (CE constraints)

Every CE constraint is enforced at admission so users cannot accidentally configure an enterprise feature.

PASS when (currently asserted via Ginkgo, scheduled for split into a dedicated `22-webhook-asserts.sh`):

- `size > 8` is rejected
- `namespaces > 2` is rejected
- `network.tls`, `xdr`, enterprise images (`aerospike-server-enterprise`), `feature-key-file` are rejected
- A duplicate `ServiceMonitor` when `monitoring.enabled=true` is rejected (#235)

### Helm chart — manifest matrix

The chart renders correctly across all supported toggle combinations and fails fast on incompatible ones.

PASS when **`scripts/40-helm-matrix.sh`** verifies all 7 modes:

| Mode | Contract |
|------|----------|
| **operator-only** (`--set ui.enabled=false`) | Operator Deployment present; NO ui-api/ui-web; NO ServiceMonitor |
| **UI full** (api + web) | api + web Deployments; NetworkPolicy with both `:8000` and `:3100`; helm-test pod present |
| **UI api-only** | api only; NetworkPolicy with ONLY `:8000`; helm-test pod present |
| **UI web-only** | web only; NetworkPolicy with ONLY `:3100`; web pod has `automountServiceAccountToken=false`; NO helm-test pod |
| **OTel disabled (default)** | `OTEL_SDK_DISABLED=true` in api env; no OTLP endpoint |
| **OTel enabled** | `OTEL_SDK_DISABLED=false`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_SAMPLER`, `OTEL_SERVICE_NAME` all set |
| **`ingress.target` failfast** | `helm template` MUST fail with an error mentioning `ui.ingress.target` |

> ⚠️ **Drift note**: The chart's current default is `ui.enabled=true`. The "operator-only" row uses `--set ui.enabled=false` explicitly to satisfy the contract — change this if the default flips.

### Helm chart — real install + helm test

`helm template` catches static regressions but misses things that only surface during apply (CRD ordering, hook race, RBAC propagation, helm-test pod regressions like #236).

PASS when **`scripts/41-helm-real-install.sh`**:

- `helm install` on a fresh namespace succeeds and pods reach Running
- `helm test <release>` reports `Phase: Succeeded`
- `helm uninstall` + namespace deletion leaves no leftover state

### UI api — CRUD smokes

The cluster-manager api is the user-facing surface for record browsing, query, sample data, and indexes. Several router-level regressions historically returned 500 instead of well-formed responses (#257–#260) — these are re-asserted on every run.

PASS when **`scripts/30-api-crud-smoke.sh`** verifies all of:

- **A. Connection lifecycle** — `POST /api/v1/connections` returns 201 + `id` + `createdAt`; `GET` list contains it; `DELETE` returns 204; subsequent `GET` returns 404.
- **B. Cluster reachability** — `GET /api/v1/clusters/{conn_id}` returns 200 with `namespaces[].name` including `test`. Confirms aerospike-py wiring inside the api pod.
- **C. sample-data partial-success** (#257) — `POST /api/v1/sample-data/{conn_id}` returns 201 with `recordsCreated`, `recordsFailed`, `indexesCreated`, `indexesFailed` keys. **Critical**: NEVER 500 even when some indexes fail.
- **D. records empty/sparse namespace** (#259) — `GET /api/v1/records/{conn_id}?ns=test&set=does-not-exist` returns 200 with `records:[]` (NOT 500).
- **E. query `pkType=auto`** (#258) — `POST /api/v1/query/{conn_id}` with `{"pkType":"auto"}` returns 200, identical behavior to omitting `pkType`.
- **F. indexes idempotency** (#260) — `POST` returns 201 with `state: building|ready`; `DELETE` returns 204; calling `DELETE` again on the same name still returns 204 (no orphaned 500).
- **G. X-Request-ID round-trip** — every response carries `x-request-id` echoing whatever the caller sent.

### UI api — K8s management create/delete

Real UI users create AerospikeCluster CRs through the api, not directly with `kubectl`. The whole `/api/v1/k8s/clusters/...` family was previously untested.

PASS when **`scripts/33-api-k8s-create-smoke.sh`**:

- `POST /api/v1/k8s/clusters` creates a 1-node CR via the api → 200/201/202
- The CR appears in `kubectl get asc` and reaches `phase=Completed`
- `GET .../{ns}/{name}` returns 200 with the right `metadata.name`
- `GET .../health` returns 200
- `GET .../yaml` returns parseable YAML
- `DELETE .../{ns}/{name}` removes the CR; subsequent `GET` returns 404

### Logging — text vs JSON, request correlation

PASS when **`scripts/31-logging.sh`**:

- Default `LOG_FORMAT=text` produces `YYYY-... INFO [logger] message` lines
- `helm upgrade --set ui.env.logFormat=json` switches every record to a JSON object with `timestamp`, `level`, `logger`, `message`, `request_id` keys
- A `curl -H "X-Request-ID: <id>"` request echoes the id in `x-request-id` response header AND embeds it as `request_id` in the matching JSON log record. Caller can correlate without server access.
- Note: the middleware-emitted access log line shows `trace_id: null, span_id: null` even when OTel is fully enabled — this is by design (the middleware writes after the OTel span closes). Logs emitted from inside route handlers carry the real trace IDs.

### OTel — opt-in env wiring + runtime export

PASS when **`scripts/32-otel-runtime.sh`**:

- `helm upgrade --set ui.api.otel.enabled=true,...endpoint=...` flips `OTEL_SDK_DISABLED=false` and sets `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_TRACES_SAMPLER`, `OTEL_SERVICE_NAME=aerospike-cluster-manager-api`.
- A deployed OpenTelemetry collector (`reference/otel-collector.yaml`) receives traces with `service.name: aerospike-cluster-manager-api`.
- **Both** `opentelemetry.instrumentation.fastapi` and `opentelemetry.instrumentation.asyncpg` instrumentation scopes appear at the collector. (Regression guard for cluster-manager #265 — the FastAPIInstrumentor fix; before that PR only asyncpg spans showed up, parent-less.)
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

## Scripts map (single source of truth)

| Script | Purpose | Last-line contract scope |
|--------|---------|--------------------------|
| `scripts/lib.sh` | Shared library: logging, asserts, kubectl/helm/podman wrappers, port-forward management, env defaults | (sourced) |
| `scripts/00-prereqs.sh` | Tool versions, podman runtime, chart reachability | `prereqs` |
| `scripts/10-kind-up.sh` | `make setup-test-e2e` + `docker-build` + `kind load` | `kind-up` |
| `scripts/11-cert-manager.sh` | Install pinned cert-manager, wait for webhook | `cert-manager` |
| `scripts/12-helm-install.sh` | Parametric `helm install` (image / OTel / log-format flags) | `helm-install` |
| `scripts/20-ginkgo.sh` | `go test ./test/e2e/` directly (preserves Kind cluster) | `ginkgo` |
| `scripts/21-asc-create-smoke.sh` | Fast 1-node create/verify/delete (PR gate, api smoke prereq) | `asc-create` |
| `scripts/30-api-crud-smoke.sh` | UI api CRUD smokes A–G | `api-crud` |
| `scripts/31-logging.sh` | text/json LOG_FORMAT + X-Request-ID correlation | `logging` |
| `scripts/32-otel-runtime.sh` | OTel collector deploy + traffic + parent/child span verification | `otel-runtime` |
| `scripts/33-api-k8s-create-smoke.sh` | api-mediated AerospikeCluster CRUD (`/api/v1/k8s/clusters/...`) | `api-k8s-create` |
| `scripts/40-helm-matrix.sh` | `helm lint` + 7-mode `helm template` matrix (no cluster needed) | `helm-matrix` |
| `scripts/41-helm-real-install.sh` | `helm install` + `helm test` + `helm uninstall` | `helm-real` |
| `scripts/60-diag-bundle.sh` | Capture cluster state, logs, CRDs, helm values, collector logs | `diag-bundle` |
| `scripts/99-cleanup.sh` | helm uninstall + namespace delete (`--kind` also deletes Kind cluster) | `cleanup` |
| `scripts/run-all.sh` | Orchestrator: `--mode {chart,smoke,full,ginkgo}`; emits Section 8 report | `run-all` |

Each script has a header comment listing inputs (env vars + flags), the eval criteria it asserts, and the contract output line. Read those before changing the script body.

---

## Reporting

`scripts/run-all.sh` emits this format (Section 8 of the legacy playbook):

```
e2e run on <branch>@<short-sha> — <date>
Mode:        chart / smoke / full / ginkgo
Duration:    <Xm Ys>
Outcome:     PASS / FAIL

Steps: N passed, M failed (of T total)
  ✅ <scope>             <pass summary>
  ❌ <scope>             <fail reason>

Failed steps: <names>
Per-step output: /tmp/run-all-<step>.out
Diagnostic bundle: /tmp/e2e-diag-<timestamp>/
```

Do not claim "all scenarios pass" without the `e2e:pass[scope=...]` line for that scope being present in the output. Historical drift between this checklist and the test file has happened before (rack-per-StatefulSet refactor renamed several Contexts).

---

## Common failures — first-look table

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `kind create cluster` hangs on macOS | Podman machine not running | `podman machine start && podman system service --time=0 &` |
| Operator pod `ImagePullBackOff` for `controller:latest` | Image not loaded into Kind | re-run `scripts/10-kind-up.sh` |
| `phase=Error` on first reconcile, no useful logs | Webhook rejected CR (server-side apply ate the message) | `kubectl get events -n <ns>` — webhook errors land there as Warning |
| `phase=BackoffActive` (not Error, not Completed) | Reconciliation Circuit Breaker tripped | `kubectl get asc -o jsonpath='{.status.conditions[?(@.type=="ReconcileBackoff")]}'`; reset by editing the CR or restarting operator |
| `helm template` fails for `ingress.target=web` + `web.enabled=false` | Chart's intentional failfast (since #236) | set `ui.ingress.target=api` or enable web |
| e2e passes locally, fails in CI | Different `CONTAINER_TOOL` (Docker vs Podman) | confirm CI sets `CONTAINER_TOOL=podman KIND_PROVIDER=podman` |
| Collector image `0.115.0` not found on docker.io | Tag rotated out | `scripts/32-otel-runtime.sh` auto-falls back to `$COLLECTOR_IMAGE` (defaults to `:latest`) and reloads |
| OTel env wired but no spans at collector | `FastAPIInstrumentor` regression | check `scripts/32-otel-runtime.sh` output for "no FastAPIInstrumentor scope" — re-apply cluster-manager #265 |

---

## When to update

- A new `Context(...)` lands in `test/e2e/` → the contract is owned by `scripts/20-ginkgo.sh` (it doesn't enumerate; the suite does), but if it tests a brand-new concern (e.g. backup), add a section above and a new `2X-foo.sh`.
- A new chart toggle is introduced (e.g. `ui.postgresql.external`) → add a new row to the M-matrix in `scripts/40-helm-matrix.sh`.
- A regression caught in production → add the smallest reproducer to the relevant script. Don't grow the markdown.
- A perf budget renegotiated → record both old and new values in the perf section.

The skill version is implicit in `git log` — don't bump anything in this file.
