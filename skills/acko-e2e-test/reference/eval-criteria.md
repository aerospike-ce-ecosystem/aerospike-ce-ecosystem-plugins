# Eval criteria — what counts as PASS (full detail)

Every section is owned by one or more pytest tests. The pytest test file is the contract — read it before changing it.

## Functional — operator + cluster lifecycle

The operator reconciles AerospikeCluster CRs through every supported lifecycle event without losing data, leaking PVCs, or leaving the CR in a non-terminal phase.

PASS when:

- **`tests/lifecycle/test_asc_create_smoke.py`** — applying `config/samples/acko_v1alpha1_aerospikecluster.yaml` results in `phase=Completed` within 5 min, the expected K8s resources exist (StatefulSet, headless Service, ConfigMap, PDB), `status.size == spec.size`, and `status.pods` reports the right number of running+ready entries. Deleting the CR removes the namespace's ASC count to 0; re-applying it returns to Completed.
- **`tests/lifecycle/test_ginkgo.py`** — the in-tree Ginkgo suite (`go test ./test/e2e/`) passes 100% with no `FAIL!` lines. Covers single-node + 3-node PVC + multi-rack 6-node + ACL/cascadeDelete + PVC create/retain/cleanup + multi-rack scale + custom metrics + perPodStatus configHash + rolling restart + scale up/down + RollingUpdateBatchSize + paused cluster + PDB enable/disable + template + drift detection. Mode selectable via `GINKGO_MODE` env var.

## Functional — webhook validation (CE constraints)

Every CE constraint is enforced at admission so users cannot accidentally configure an enterprise feature.

PASS when (currently asserted via the in-tree Ginkgo suite, scheduled for split into `tests/lifecycle/test_webhook.py`):

- `size > 8` is rejected
- `namespaces > 2` is rejected
- duplicate namespace name, CE image `< ce-8` (incl. dotless `ce-7`), enterprise logging context (`audit`/`report-*`), scoped admin privilege (`sys-admin.ns`), malformed ACL scope, invalid `serviceMonitor.interval`/labels, and per-rack `aerospikeConfig` CE violations are all rejected (see `acko-operations/reference/validation-rules.md`)
- `network.tls`, `xdr`, enterprise images (`aerospike-server-enterprise`), `feature-key-file` are rejected
- A duplicate `ServiceMonitor` when `monitoring.enabled=true` is rejected (#235)

## Helm chart — manifest matrix

The chart renders correctly across every supported toggle combination and fails fast on incompatible ones.

PASS when **`tests/chart/test_helm_matrix.py`** verifies the matrix:

| Mode | Contract |
|------|----------|
| **operator-only** (`--set ui.api.enabled=false --set ui.web.enabled=false`) | Operator Deployment present; NO ui-api/ui-web; NO ServiceMonitor |
| **UI full** (api + web) | api + web Deployments; NetworkPolicy with both `:8000` and `:3100`; helm-test pod present |
| **UI api-only** | api only; NetworkPolicy with ONLY `:8000`; helm-test pod present |
| **UI web-only** | web only; NetworkPolicy with ONLY `:3100`; web pod has `automountServiceAccountToken=false`; NO helm-test pod |
| **OTel disabled (default)** | `OTEL_SDK_DISABLED=true` in api env; no OTLP endpoint |
| **OTel enabled** | `OTEL_SDK_DISABLED=false`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACES_SAMPLER`, `OTEL_SERVICE_NAME` all set |
| **Operator OTel enabled** | `observability.otel.enabled=true` → operator Deployment env has `OTEL_SDK_DISABLED=false` + `OTEL_EXPORTER_OTLP_ENDPOINT`; NetworkPolicy / CiliumNetworkPolicy gain an OTLP egress rule on `observability.otel.collectorPort` |
| **`ingress.target` failfast** | `helm template` MUST fail with an error mentioning `ui.ingress.target` |

Plus **`tests/chart/test_helm_lint.py`** — `helm lint` reports no `[ERROR]` entries.

> ⚠️ **Drift note**: Chart 0.4.0 removed the legacy `ui.enabled` master switch. The UI is controlled by the independent `ui.api.enabled` / `ui.web.enabled` toggles (both default `true`); the "operator-only" row opts out by setting BOTH to `false`. If a future chart re-introduces a master switch, update the parametrize entries.

## Helm chart — real install + helm test

`helm template` catches static regressions but misses things that only surface during apply (CRD ordering, hook race, RBAC propagation, hanging helm-test pods like #236).

PASS when **`tests/chart/test_helm_real_install.py`**:

- `helm install` on a fresh namespace succeeds and pods reach Running
- `helm test <release>` reports `Phase: Succeeded`
- `helm uninstall` + namespace deletion leaves no leftover state

## UI api — CRUD smokes

The cluster-manager api is the user-facing surface for record browsing, query, sample data, and indexes. Several router-level regressions historically returned 500 instead of well-formed responses (#257–#260) — these are re-asserted on every run as `regression_guard` tests.

PASS when **`tests/api/test_api_crud.py`** verifies all of:

- **A. Connection lifecycle** — `POST /api/v1/connections` returns 201 + `id` + `createdAt`; `GET` list contains it; `DELETE` returns 204; subsequent `GET` returns 404.
- **B. Cluster reachability** — `GET /api/v1/clusters/{conn_id}` returns 200 with `namespaces[].name` including `test`. Confirms aerospike-py wiring inside the api pod.
- **C. sample-data partial-success** (#257) — `POST /api/v1/sample-data/{conn_id}` returns 201 with `recordsCreated`, `recordsFailed`, `indexesCreated`, `indexesFailed` keys. **Critical**: NEVER 500 even when some indexes fail.
- **D. records empty/sparse namespace** (#259) — `GET /api/v1/records/{conn_id}?ns=test&set=does-not-exist` returns 200 with `records:[]` (NOT 500).
- **E. query `pkType=auto`** (#258) — `POST /api/v1/query/{conn_id}` with `{"pkType":"auto"}` returns 200, identical behavior to omitting `pkType`.
- **F. indexes idempotency** (#260) — `POST` returns 201 with `state: building|ready`; `DELETE` returns 204; calling `DELETE` again on the same name still returns 204 (no orphaned 500).
- **G. X-Request-ID round-trip** — every response carries `x-request-id` echoing whatever the caller sent.

## UI api — K8s management create/delete

Real UI users create AerospikeCluster CRs through the api, not directly with `kubectl`. The whole `/api/v1/k8s/clusters/...` family was previously untested in e2e.

PASS when **`tests/api/test_api_k8s_create.py`**:

- `POST /api/v1/k8s/clusters` creates a 1-node CR via the api → 200/201/202
- The CR appears in `kubectl get asc` and reaches `phase=Completed`
- `GET .../{ns}/{name}` returns 200 with the right `metadata.name`
- `GET .../health` returns 200
- `GET .../yaml` returns parseable YAML
- `DELETE .../{ns}/{name}` removes the CR; subsequent `GET` returns 404

## Logging — text vs JSON, request correlation

PASS when **`tests/observability/test_logging.py`**:

- Default `LOG_FORMAT=text` produces `YYYY-... INFO [logger] message` lines
- `helm upgrade --set ui.env.logFormat=json` switches every record to a JSON object with `timestamp`, `level`, `logger`, `message`, `request_id` keys
- A `curl -H "X-Request-ID: <id>"` request echoes the id in `x-request-id` response header AND embeds it as `request_id` in the matching JSON log record. Caller can correlate without server access.
- Note: the middleware-emitted access log line shows `trace_id: null, span_id: null` even when OTel is fully enabled — this is by design (the middleware writes after the OTel span closes). Logs emitted from inside route handlers carry the real trace IDs.

## OTel — opt-in env wiring + runtime export

PASS when **`tests/observability/test_otel_runtime.py`** (regression_guard for cluster-manager #265):

- `helm upgrade --set ui.api.otel.enabled=true,...endpoint=...` flips `OTEL_SDK_DISABLED=false` and sets `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL`, `OTEL_TRACES_SAMPLER`, `OTEL_SERVICE_NAME=aerospike-cluster-manager-api`.
- A deployed OpenTelemetry collector (`reference/otel-collector.yaml`) receives traces with `service.name: aerospike-cluster-manager-api`.
- **Both** `opentelemetry.instrumentation.fastapi` and `opentelemetry.instrumentation.asyncpg` instrumentation scopes appear at the collector. Before #265 only asyncpg spans showed up, parent-less.
- At least one trace contains a Server-kind FastAPI span (HTTP request) **and** an asyncpg child span sharing the same trace ID — proving HTTP→DB context propagation.

**Operator side** (`observability.otel.*`) follows the same pattern: `helm upgrade --set observability.otel.enabled=true --set observability.otel.endpoint=<host:4317>` sets `OTEL_SDK_DISABLED=false` on the operator Deployment, and when `networkPolicy.enabled` / `cilium.enabled` is set the chart auto-adds the OTLP egress rule (`observability.otel.collectorPort`). Verified end-to-end on a Calico kind cluster (acko #281): operator reconcile spans, `acko_*` + controller-runtime metrics, and operator logs reach the collector — and removing the egress rule blocks export (negative control). A scheme-less endpoint is normalized to `http://`; the chart never deploys a collector.

## Performance / soak (release-tag only)

These are **not** gated on every PR but are required before tagging a minor release. Currently captured as TODOs; record results in `project-hub/docs/docs/history/releases/<version>/perf.md`.

PASS targets:

- **Reconcile loop** — 6-node multi-rack, 10× no-op `kubectl edit` → p99 reconcile < 2 s, circuit breaker stays Closed.
- **Rolling restart** — 8-node + `RollingUpdateBatchSize=2` → restart in `(size/batchSize) × (warm_restart + 30s)`, no `BackoffActive`.
- **Scale-up burst** — 1 → 8 nodes in one patch → all Ready < 5 min on Kind, no PVC stuck.
- **Webhook latency** — `kubectl apply` 100 invalid CRs in a tight loop → 100% rejected, no API server timeout, operator stays Ready.
- **Memory ceiling** — 1h soak under 6-node multi-rack → operator RSS < 256 MiB, no OOM, no fd leak.
- **OTel egress when disabled** — default install + `tcpdump :4317,4318` for 10 min → 0 packets.
