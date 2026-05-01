---
name: acko-e2e-test
description: "MUST USE for ACKO end-to-end testing on Kind/local clusters. Contains the canonical scenario list (deploy, scale, rolling update, multi-rack, ACL, PVC, Helm chart split-mode, OTel observability), Ginkgo label conventions (`heavy` vs default), the project's mandatory `helm install`-based operator setup (NOT `make run-local`/`make deploy` — those bypass the real user install path), and performance-check procedures the project expects every release to verify. Without this skill, e2e runs miss scenarios that have caught regressions historically (CE 8.1 data-size rename, webhook duplicate ServiceMonitor, helm test pod in web-only mode, circuit-breaker BackoffActive) and they may install the operator via paths real users never take. Triggers on: ACKO e2e test, kind cluster test, make test-e2e, release verification, performance test for Aerospike operator, helm chart test, post-merge smoke test, regression checklist."
---

# ACKO End-to-End Test Playbook

Canonical scenarios + performance checks the ACKO project expects to pass before each release. Run from the operator repo root (`aerospike-ce-kubernetes-operator/`). Most scenarios run inside a Kind cluster spawned by `make setup-test-e2e`.

---

## 0. Prerequisites

```bash
# Required tools
command -v kind go podman kubectl helm    # all must resolve
go version                                # >= 1.25
kind --version                            # >= 0.31
podman machine list                       # machine must be Running
```

CLAUDE.md (repo root) note — Podman is the project's container runtime. Set `CONTAINER_TOOL=podman KIND_PROVIDER=podman` for every e2e invocation. Do NOT swap to Docker without a recorded ADR.

---

## 1. Operator Install — use `helm install`, NOT `make run-local` / `make deploy`

**This is the project's most important e2e rule.** Real users install the operator via the Helm chart at `charts/aerospike-ce-kubernetes-operator/`. e2e runs MUST exercise that same path so chart-level regressions (RBAC scope, CRD bundling, value defaults, namespace handling, helper templates) get caught before release.

Forbidden during e2e (these bypass the chart entirely):
- `make run-local` — runs the controller as a host process against the cluster's API. Skips RBAC, the chart, and image loading.
- `make deploy` — applies in-tree `config/` manifests directly with kustomize. Skips the chart, helper templates, and `values.yaml` defaults.

Required setup (run after `make setup-test-e2e` brings up the Kind cluster):

```bash
# 1. Build and load the operator image into Kind
make docker-build IMG=acko-controller:e2e CONTAINER_TOOL=podman
kind load docker-image acko-controller:e2e --name aerospike-ce-kubernetes-operator-test-e2e

# 2. Install CRDs (the chart does not bundle CRDs by default for safety)
make install

# 3. Helm install the operator chart — exactly as a user would
helm install acko ./charts/aerospike-ce-kubernetes-operator \
  --namespace aerospike-operator --create-namespace \
  --set image.repository=acko-controller --set image.tag=e2e \
  --set image.pullPolicy=Never \
  --wait --timeout 5m

# 4. Verify it came up via the chart, not via leftover state
kubectl get deploy -n aerospike-operator -l app.kubernetes.io/instance=acko
helm list -n aerospike-operator
```

**Known gap**: at the time of writing, `test/e2e/e2e_suite_test.go:BeforeSuite` calls `make deploy`, not `helm install`. Until that is migrated, run e2e in two layers:

1. Helm-install layer (manual/scripted, per the steps above) — confirms the chart works.
2. Ginkgo layer (`make test-e2e` for scenario coverage) — accept that it currently uses `make deploy` for the controller. File a follow-up to migrate `BeforeSuite` to `helm install`.

For chart-only validation that doesn't need the controller running, see Section 4 (`helm template` / `helm lint`) — that lane is fast and catches most chart regressions without spinning a Kind cluster.

---

## 2. Run Modes — pick before invoking

| Mode | Command | When to use |
|------|---------|-------------|
| **Smoke** (no `heavy`) | `make test-e2e GINKGO_FLAGS='--label-filter="!heavy"'` | PR validation, fast (~5-8 min) |
| **Full** (default) | `make test-e2e` | Pre-release, post-rebase, weekly main | 
| **Single suite** | `go test -tags=e2e -run TestE2E -ginkgo.focus="Multi-rack" ./test/e2e/` | Iterating on one scenario |
| **Heavy only** | `make test-e2e GINKGO_FLAGS='--label-filter="heavy"'` | Soak / performance lane |

`heavy` label = scenarios that take >2 min, create PVCs, or scale ≥3 nodes. They're skipped in PR CI but mandatory before tagging a release.

Heavy is applied at two levels in `test/e2e/`:
- **Suite-level** (`var _ = Describe("X", Ordered, Label("heavy"), …)`): every scenario in `e2e_multirack_test.go`, `e2e_pvc_test.go`, and `e2e_template_test.go` is heavy by default.
- **Context-level** (`Context("Y", Label("heavy"), …)`): used inside `e2e_cluster_test.go` and `e2e_features_test.go` to mark specific contexts as heavy while leaving siblings on the smoke lane.

Either form satisfies `--label-filter`. Don't reason about heavy scope from a per-row annotation in this skill alone — confirm against the test file.

---

## 3. Functional Scenarios — must pass

Each row corresponds to a Ginkgo `Context` in `test/e2e/`. Status = green/red of the most recent `make test-e2e` you ran. Verify file:line still exists before claiming a scenario is covered (test names rot — see "Before recommending from memory" in the global CLAUDE.md).

### Cluster lifecycle (`e2e_cluster_test.go`)

- [ ] **Basic single-node cluster** — deploys, reaches `phase=Completed`, creates expected K8s resources (StatefulSet, ConfigMap, headless Service, PDB), populates `status.pods` correctly. Default lane.
- [ ] **3-node cluster with PV storage** (`heavy`) — 3 pods, 3 PVCs, status reports cluster size + replication factor.
- [ ] **Multi-rack 6-node cluster** (`heavy`) — 3 StatefulSets (one per rack), pods carry rack labels, 3 ConfigMaps, `status.size=6`, rack-distribution affinity is honored.
- [ ] **ACL/Storage sample with cascadeDelete** (`heavy`) — admin user from Secret, PVCs created, cluster delete cleans PVCs. Confirms ACL Secret reconciliation does not block readiness.

### Multi-rack specific (`e2e_multirack_test.go`) — entire suite is `heavy`
- [ ] **Basic multi-rack deployment** — verifies StatefulSet count, pod-to-rack mapping, rack-aware service endpoints.
- [ ] **Multi-rack scale up** — increase `spec.size`, pods land on the rack with capacity, no rebalance loop.

### PVC management (`e2e_pvc_test.go`) — entire suite is `heavy`
- [ ] **PVC creation for storage volumes** — PVC name pattern `<cluster>-<rackID>-<podOrdinal>`, status reflects bound state.
- [ ] **CascadeDelete PVC cleanup** — `cascadeDelete: true` removes PVCs on cluster delete.
- [ ] **Retained PVCs without cascadeDelete** — `cascadeDelete: false` (default) keeps PVCs after cluster delete; reattach on recreate.

### Cluster templates (`e2e_template_test.go`) — entire suite is `heavy`
- [ ] **Create cluster from template** — `AerospikeClusterTemplate` (cluster-scoped) → `AerospikeCluster` references it, fields are inherited correctly.
- [ ] **Template drift detection** — modifying the template surfaces drift in `status.conditions`.

### Enhanced features (`e2e_features_test.go`)
- [ ] **Prometheus Custom Metrics** — `acko_*` metrics scrape on `:8080/metrics` after a cluster is created. Smoke lane.
- [ ] **Per-Pod Status (configHash + podSpecHash)** — `status.pods[*].configHash` matches the pod annotation; `podSpecHash` reflects template hash. Smoke lane.
- [ ] **Config change triggers Rolling Restart** (`heavy`) — patch `spec.aerospikeConfig`, pods restart in order, `phase` flows `Updating → Completed`.
- [ ] **Scale Up and Down** (`heavy`) — `spec.size` change scales StatefulSet, `status.size` matches, no orphaned PVCs on scale-down + cascadeDelete.
- [ ] **RollingUpdateBatchSize** (`heavy`) — `spec.rollingUpdate.batchSize=2` actually deletes 2 pods at a time during a config change.
- [ ] **Paused Cluster** (`heavy`) — `spec.paused=true` halts reconciliation; resume continues from where it stopped. Phase reports `Paused`.
- [ ] **PodDisruptionBudget** (`heavy`) — PDB is created by default for every cluster; setting `spec.disablePDB=true` deletes it on the next reconcile. (Verify against `e2e_features_test.go` "PodDisruptionBudget" Context.)

### Webhook validation (covered by unit tests, but smoke-check during e2e)
- [ ] CE constraint violations are rejected at admission: `size>8`, `namespaces>2`, `network.tls`, `xdr`, enterprise image (`aerospike-server-enterprise`), `feature-key-file`. Each must surface a clear error string.
- [ ] Duplicate ServiceMonitor when `monitoring.enabled=true` is rejected (added in #235).

---

## 4. Helm Chart Scenarios — `helm template` + `helm lint`

Run from `charts/aerospike-ce-kubernetes-operator/`. These are NOT in `test/e2e/`; they're a separate gate that catches chart regressions like the split-mode toggle bugs from PR #236.

```bash
cd charts/aerospike-ce-kubernetes-operator && helm lint .
```

For each mode below, run `helm template foo . --set <args>` and verify the listed resources / properties exist:

| Mode | Set args | Must exist | Must NOT exist |
|------|----------|------------|----------------|
| Operator only | (defaults) | Operator Deployment, CRD, ClusterRole | UI Deployment, ServiceMonitor |
| UI full (api+web) | `ui.enabled=true,ui.networkPolicy.enabled=true,ui.tests.enabled=true` | api Deployment, web Deployment, both Services, NetworkPolicy with both ports (`8000` + `3100`), helm-test pod | — |
| UI api-only | `ui.enabled=true,ui.web.enabled=false,ui.ingress.target=api,ui.networkPolicy.enabled=true,ui.tests.enabled=true` | api Deployment, api Service, NetworkPolicy with ONLY `:8000`, helm-test pod | web Deployment, web Service |
| UI web-only | `ui.enabled=true,ui.api.enabled=false,ui.web.env.apiUrl=http://x,ui.networkPolicy.enabled=true,ui.tests.enabled=true` | web Deployment, web Service, NetworkPolicy with ONLY `:3100`, web Pod has `automountServiceAccountToken: false` | api Deployment, api Service, helm-test pod |
| OTel disabled (default) | `ui.enabled=true` | api env contains `OTEL_SDK_DISABLED=true` | (no `OTEL_EXPORTER_OTLP_ENDPOINT`) |
| OTel enabled | `ui.enabled=true,ui.api.otel.enabled=true,ui.api.otel.endpoint=http://col:4317` | api env contains `OTEL_SDK_DISABLED=false` AND `OTEL_EXPORTER_OTLP_ENDPOINT=http://col:4317` AND `OTEL_TRACES_SAMPLER` | — |
| ingress.target failfast | `ui.enabled=true,ui.web.enabled=false,ui.ingress.enabled=true` (default `target=web`) | `helm template` must FAIL with a clear error pointing at `ui.ingress.target` | — |

A successful chart pass = `helm lint` clean + every row above renders / fails as documented.

Beyond `helm template`, run a real `helm install` against the Kind cluster at least once per release to catch issues that only surface during apply (CRD ordering, hook race, RBAC propagation):

```bash
helm install acko-test ./charts/aerospike-ce-kubernetes-operator \
  --namespace aerospike-operator-test --create-namespace \
  --wait --timeout 5m
helm test acko-test -n aerospike-operator-test          # runs the bundled test pods
helm uninstall acko-test -n aerospike-operator-test
kubectl delete ns aerospike-operator-test
```

`helm test` is what surfaces the `tests/test-api-connectivity.yaml` regression discussed in PR #236 — the helm-template lane alone won't catch a hanging test pod.

---

## 5. Performance / Soak Checks

These don't gate PRs but are required before tagging a minor release. Record results in `project-hub/docs/docs/history/releases/<version>/perf.md`.

| Check | How | Acceptance |
|-------|-----|------------|
| Reconcile loop budget | Enable operator metrics, deploy a 6-node multi-rack, run `kubectl edit asc` 10× with no-op edits | p99 reconcile duration < 2 s; circuit breaker stays in `Closed` |
| Rolling restart cadence | 8-node cluster + `RollingUpdateBatchSize=2`, trigger config change | Restart completes in `(size / batchSize) * (warm_restart_seconds + 30s)`; no `BackoffActive` |
| Scale-up burst | Single-node → 8-node in one patch | All pods `Ready` < 5 min on Kind; PVC creation does not block |
| Webhook latency | `kubectl apply` 100 invalid CRs in a tight loop | 100% rejected, no API-server timeout, operator stays `Ready` |
| Memory ceiling | Operator pod under 6-node multi-rack soak (1h) | RSS < 256 MiB; no OOM, no fd leak |
| OTel egress when disabled | Default install + `tcpdump -i any port 4317 or port 4318` for 10 min | 0 packets — confirms `OTEL_SDK_DISABLED=true` actually short-circuits |

---

## 6. Diagnostic Bundle on Failure

When any scenario fails, capture this BEFORE running `make cleanup-test-e2e` (which deletes the Kind cluster):

```bash
# 1. Operator + workload state
kubectl get pods,asc,statefulset,configmap,pvc,pdb -A -o wide > /tmp/e2e-state.txt
kubectl describe asc -A > /tmp/e2e-describe.txt
kubectl logs -n aerospike-operator -l control-plane=controller-manager --tail=2000 > /tmp/e2e-operator.log

# 2. Failing pod
kubectl logs -n <ns> <failing-pod> --previous > /tmp/e2e-pod.log 2>&1 || true
kubectl describe pod -n <ns> <failing-pod> > /tmp/e2e-pod-describe.txt

# 3. Events (chronological)
kubectl get events -A --sort-by='.lastTimestamp' > /tmp/e2e-events.txt

# 4. CRD + webhook config
kubectl get crd aerospikeclusters.acko.io -o yaml > /tmp/e2e-crd.yaml
kubectl get validatingwebhookconfiguration -o yaml > /tmp/e2e-webhook.yaml
```

Attach all of `/tmp/e2e-*` to the failing PR / issue. Then run `make cleanup-test-e2e`.

---

## 7. Common Failures — first-look table

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `kind create cluster` hangs on macOS | Podman machine not running, or rootful socket missing | `podman machine start && podman system service --time=0 &` |
| Operator pod `ImagePullBackOff` for `controller:latest` | `make docker-build` skipped, image not loaded into Kind | `make docker-build IMG=... && kind load docker-image ...` |
| `phase=Error` on first reconcile, no useful logs | Webhook rejected the CR but kubectl apply was server-side | check `kubectl get events`; webhook errors land there as Warning |
| `phase=BackoffActive` (not Error, not Completed) | Reconciliation Circuit Breaker tripped after repeated failures | dump `status.conditions[?(@.type=="ReconcileBackoff")]`; reset by editing the CR or restarting the operator |
| Helm template fails for `ingress.target=web` + `web.enabled=false` | This is the chart's own failfast (intentional, since #236) | set `ui.ingress.target=api` or enable web |
| e2e test passes locally, fails in CI | Different `CONTAINER_TOOL` (Docker vs Podman) | confirm the workflow sets `CONTAINER_TOOL=podman KIND_PROVIDER=podman` |

---

## 8. Reporting Format

After a run, summarize for the user in this exact shape:

```
e2e run on <branch>@<short-sha> — <date>
Mode:        smoke / full / heavy-only
Duration:    <Xm>
Outcome:     PASS / FAIL

Functional:  N/M scenarios passed
Helm chart:  N/M modes verified
Performance: <list>

Failures (if any):
  - <Context name> — <one-line cause> — <link to logs>
```

Do NOT claim "all scenarios pass" without listing the file paths you verified — historical drift between the test file and this checklist has happened before (e.g. when scenarios were renamed during the rack-per-StatefulSet refactor).

---

## 9. When to Update This Playbook

Add a new row whenever:
- A new `Context(...)` is added in `test/e2e/`
- A new chart-level toggle is introduced (e.g. the `ui.api.enabled` / `ui.web.enabled` split in #236, or future `ui.postgresql.external`)
- A regression is caught in production that the existing checklist did not surface — add the smallest possible reproducer
- A performance budget is renegotiated — the previous value goes into the table footnote so future-us can spot drift

Skill version is implicit (commit hash). Don't bump anything in this file; the git log is the changelog.
