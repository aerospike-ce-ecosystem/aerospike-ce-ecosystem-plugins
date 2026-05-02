# ACKO e2e — Quick Commands

Reference snippets for the scenarios listed in `SKILL.md`. Pull these in only when actually running the corresponding check; they're separated to keep the SKILL frontmatter scannable.

## Kind cluster lifecycle

```bash
# Fresh cluster from the project's kind-config.yaml (3-worker, zone labels)
make setup-kind                                                # name: kind
make setup-test-e2e                                            # name: aerospike-ce-kubernetes-operator-test-e2e

# Drop the e2e cluster
make cleanup-test-e2e

# Drop everything (use when state is wedged)
kind get clusters | xargs -I{} kind delete cluster --name {}
```

## Run a single Ginkgo scenario

```bash
go test -tags=e2e -timeout 30m ./test/e2e/ -v \
  -ginkgo.v \
  -ginkgo.focus="Multi-rack 6-node cluster"
```

`-ginkgo.focus` accepts a regex against `Describe / Context / It` names. Combine with `-ginkgo.skip` to exclude.

## Verify scaffolded resources for a basic 1-node cluster

```bash
NS=aerospike
NAME=test
kubectl get asc -n $NS $NAME -o jsonpath='{.status.phase}'                 # "Completed"
kubectl get sts -n $NS -l app.kubernetes.io/instance=$NAME                  # one StatefulSet
kubectl get cm -n $NS -l app.kubernetes.io/instance=$NAME                   # one ConfigMap
kubectl get svc -n $NS -l app.kubernetes.io/instance=$NAME                  # headless service
kubectl get pdb -n $NS                                                       # PDB
kubectl get pod -n $NS -o jsonpath='{.items[*].metadata.annotations.acko\.io/config-hash}'   # configHash matches status.pods[*].configHash
```

## End-to-end Helm install (real user path)

```bash
# 1. Build operator image (Podman is the project default)
make docker-build IMG=acko-controller:e2e CONTAINER_TOOL=podman

# 2. Load image into Kind via tarball — `kind load docker-image` is unreliable
#    on the kind+podman provider; the tarball path works everywhere.
podman save -o /tmp/acko-controller-e2e.tar localhost/acko-controller:e2e
KIND_EXPERIMENTAL_PROVIDER=podman \
  kind load image-archive /tmp/acko-controller-e2e.tar \
  --name aerospike-ce-kubernetes-operator-test-e2e

# 3. cert-manager is REQUIRED — chart renders Certificate/Issuer for the webhook
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.19.3/cert-manager.yaml
kubectl wait deployment/cert-manager-webhook --for=condition=Available -n cert-manager --timeout=5m
sleep 10

# 4. Helm install — CRDs come from the aerospike-ce-kubernetes-operator-crds
#    subchart, so do NOT run `make install` first (it would block helm
#    install with an ownership-label mismatch).
helm install acko ./charts/aerospike-ce-kubernetes-operator \
  --namespace aerospike-operator --create-namespace \
  --set image.repository=localhost/acko-controller \
  --set image.tag=e2e \
  --set image.pullPolicy=Never \
  --wait --timeout 5m

# 5. Real-user smoke (helm-bundled tests)
helm test acko -n aerospike-operator

# 6. Tear down via helm (mirrors uninstall flow)
helm uninstall acko -n aerospike-operator
kubectl delete ns aerospike-operator
```

> Do NOT substitute `make run-local` or `make deploy` for these steps. Those skip the chart and miss regressions in helper templates / values defaults / RBAC scope. Section 1 of the SKILL explains why.

## Helm template scenario assertions

```bash
cd charts/aerospike-ce-kubernetes-operator

# Resource counts (use as a sanity check; exact numbers depend on chart version)
helm template t . --set ui.enabled=true --set ui.networkPolicy.enabled=true --set ui.tests.enabled=true --set ui.ingress.enabled=true | grep -cE "^kind:"
# expect: ~33 (full)

helm template t . --set ui.enabled=true --set ui.web.enabled=false --set ui.ingress.target=api --set ui.networkPolicy.enabled=true --set ui.tests.enabled=true --set ui.ingress.enabled=true | grep -cE "^kind:"
# expect: ~31 (api-only, no web Deployment / Service)

helm template t . --set ui.enabled=true --set ui.api.enabled=false --set ui.web.env.apiUrl=http://x --set ui.networkPolicy.enabled=true --set ui.tests.enabled=true --set ui.ingress.enabled=true | grep -cE "^kind:"
# expect: ~26 (web-only, no api Deployment / Service / helm-test pod)
```

NetworkPolicy port stanza assertions:

```bash
helm template t . --set ui.enabled=true --set ui.web.enabled=false --set ui.networkPolicy.enabled=true | awk '/kind: NetworkPolicy/,/---/' | grep "port:"
# expect: only :8000

helm template t . --set ui.enabled=true --set ui.api.enabled=false --set ui.web.env.apiUrl=http://x --set ui.networkPolicy.enabled=true | awk '/kind: NetworkPolicy/,/---/' | grep "port:"
# expect: only :3100
```

`automountServiceAccountToken` assertion (web pod):

```bash
helm template t . --set ui.enabled=true | awk '/name: web/,/---/' | grep automountServiceAccountToken
# expect: false
```

ingress.target failfast:

```bash
helm template t . --set ui.enabled=true --set ui.web.enabled=false --set ui.ingress.enabled=true 2>&1 | grep -i "ingress.target"
# expect: explicit error from ingress.yaml:11 telling the user to flip the target
```

## Operator metrics

```bash
# port-forward and curl
kubectl -n aerospike-operator port-forward svc/aerospike-ce-kubernetes-operator-controller-manager-metrics-service 8443:8443 &
curl -k https://localhost:8443/metrics | grep "^acko_"
```

Expected metric names (substrings, asserted by `e2e_features_test.go:81-85`):

```
acko_cluster_phase
acko_cluster_ready_pods
acko_reconcile_duration_seconds
```

The operator may expose other `acko_*` metrics (e.g. circuit-breaker state) but only the three above are e2e-asserted. If you want to verify an additional metric, add the assertion to the test before relying on it here.

## Rolling restart drill

```bash
# Force a no-op rolling restart by patching an annotation
kubectl patch asc -n $NS $NAME --type=merge -p '{"spec":{"podSpec":{"metadata":{"annotations":{"acko.io/restart-trigger":"'"$(date +%s)"'"}}}}}'

# Watch pod ages (ordered: largest ordinal restarts first by default)
kubectl get pod -n $NS -l app.kubernetes.io/instance=$NAME -w
```

## Webhook smoke

```bash
# Each of these must produce an admission rejection with a clear message
kubectl apply -f - <<'EOF'
apiVersion: acko.io/v1alpha1
kind: AerospikeCluster
metadata: { name: bad-size, namespace: aerospike }
spec:
  size: 9                               # CE max is 8 — must reject
  image: aerospike/aerospike-server:ce-8.1.1.1
  aerospikeConfig: { namespaces: [{ name: test, replication-factor: 1, storage-engine: { type: memory } }] }
EOF

kubectl apply -f - <<'EOF'
apiVersion: acko.io/v1alpha1
kind: AerospikeCluster
metadata: { name: bad-image, namespace: aerospike }
spec:
  size: 1
  image: aerospike/aerospike-server-enterprise:8.1.1.1   # EE image — must reject
  aerospikeConfig: { namespaces: [{ name: test, replication-factor: 1, storage-engine: { type: memory } }] }
EOF
```

## Circuit breaker observation

```bash
# Trigger by editing CRD into invalid state repeatedly
for i in $(seq 1 10); do
  kubectl patch asc -n $NS $NAME --type=merge -p '{"spec":{"size":'$((9 + i))'}}' || true
done

# Watch breaker state in status (introduced in PR #234)
kubectl get asc -n $NS $NAME -o jsonpath='{.status.conditions[?(@.type=="ReconcileBackoff")]}{"\n"}'
```

## OTel "really disabled" check

```bash
# In Kind, watch for any traffic to common OTel collector ports while operator runs idle
sudo tcpdump -i any -n 'port 4317 or port 4318' &
TCPDUMP_PID=$!
sleep 60
kill $TCPDUMP_PID
# expect: 0 packets captured (or only loopback traffic if a local collector exists)
```

## API CRUD smoke

End-to-end CRUD against the live ui-api. Assumes:
- `helm install` per Section 1 has run
- An `AerospikeCluster` named `aerospike-basic` is `phase=Completed` in namespace `aerospike` (the basic single-node from Section 3)
- A port-forward `localhost:18000 → ui-api:80` is active

```bash
NS=aerospike-operator
kubectl port-forward -n $NS svc/acko-aerospike-ce-kubernetes-operator-ui-api 18000:80 &
PF=$!
sleep 2
API=http://localhost:18000

set -euo pipefail
trap 'kill $PF 2>/dev/null || true' EXIT

# --- 1. Connection lifecycle (DB persistence) ---
echo "[1] create connection"
CREATE=$(curl -fsS -X POST $API/api/v1/connections \
  -H "Content-Type: application/json" \
  -d '{"name":"smoke","hosts":["aerospike-basic.aerospike.svc.cluster.local"],"port":3000,"clusterName":"aerospike-basic","color":"#0097D3"}')
CONN_ID=$(echo "$CREATE" | jq -r .id)
echo "    conn_id=$CONN_ID"

echo "[1] list contains the new connection"
curl -fsS $API/api/v1/connections | jq -e ".[] | select(.id==\"$CONN_ID\")" >/dev/null

# --- 2. Cluster reachability (aerospike-py wiring) ---
echo "[2] GET /api/v1/clusters/$CONN_ID"
curl -fsS $API/api/v1/clusters/$CONN_ID | jq -e '.namespaces | map(.name) | contains(["test"])' >/dev/null

# --- 3. sample-data partial-success contract (#257) ---
echo "[3] POST /api/v1/sample-data — must 201, never 500"
curl -fsS -X POST $API/api/v1/sample-data/$CONN_ID \
  -H "Content-Type: application/json" \
  -d '{"namespace":"test","setName":"smoke","recordCount":10}' | \
  jq -e 'has("recordsCreated") and has("recordsFailed") and has("indexesCreated") and has("indexesFailed")' >/dev/null

# --- 4. records on empty namespace (#259) ---
# Use a different set that does NOT exist — must return empty page, not 500.
echo "[4] GET /api/v1/records on empty set — must 200 with records=[]"
curl -fsS "$API/api/v1/records/$CONN_ID?ns=test&set=does_not_exist&pageSize=3" | \
  jq -e '.records == [] and .hasMore == false' >/dev/null

# --- 5. query with pkType=auto (#258) ---
echo "[5] POST /api/v1/query with pkType=auto — must 200, identical to omitting"
WITH=$(curl -fsS -X POST $API/api/v1/query/$CONN_ID \
  -H "Content-Type: application/json" \
  -d '{"namespace":"test","maxRecords":3,"pkType":"auto"}' | jq -S .)
WITHOUT=$(curl -fsS -X POST $API/api/v1/query/$CONN_ID \
  -H "Content-Type: application/json" \
  -d '{"namespace":"test","maxRecords":3}' | jq -S 'del(.executionTimeMs)')
diff <(echo "$WITH" | jq 'del(.executionTimeMs)') <(echo "$WITHOUT") >/dev/null

# --- 6. indexes create + delete idempotency (#260) ---
IDX=qa_smoke_$(date +%s)
echo "[6] POST /api/v1/indexes/$CONN_ID name=$IDX — must 201"
curl -fsS -X POST $API/api/v1/indexes/$CONN_ID \
  -H "Content-Type: application/json" \
  -d "{\"namespace\":\"test\",\"set\":\"smoke\",\"bin\":\"bin_int\",\"name\":\"$IDX\",\"type\":\"numeric\"}" | \
  jq -e '.state == "building" or .state == "ready"' >/dev/null
sleep 2
echo "[6] DELETE /api/v1/indexes/$CONN_ID name=$IDX — must 204"
curl -fsS -o /dev/null -w "%{http_code}\n" -X DELETE "$API/api/v1/indexes/$CONN_ID?name=$IDX&ns=test" | grep -q '^204$'

# --- 7. 500 envelope shape (#261 follow-up) ---
# /api/v1/clusters/<bogus> 404 (not a 500), so trigger a real error path.
# Easiest: hit a route with an unreachable in-DB connection by deleting first.
echo "[7] verify 500 body carries detail + requestId + error when something genuinely fails"
# (smoke skip — most happy paths above already return 2xx; do this when investigating
#  a 5xx, not as an active assertion.)

# --- 8. Cleanup connection ---
echo "[8] cleanup"
curl -fsS -o /dev/null -w "%{http_code}\n" -X DELETE $API/api/v1/connections/$CONN_ID | grep -q '^204$'
curl -fsS -o /dev/null -w "%{http_code}\n" $API/api/v1/connections/$CONN_ID | grep -q '^404$'

echo "API CRUD smoke: PASS"
```

If any step fails the script aborts (`set -e`); the port-forward is cleaned up by the trap. Each step is annotated with the issue number so a future failure points straight at the regression.

## Cleanup checklist between runs

```bash
kubectl delete asc -A --all --wait=false
kubectl delete pvc -A -l app.kubernetes.io/managed-by=aerospike-operator --wait=false
make cleanup-test-e2e
```
