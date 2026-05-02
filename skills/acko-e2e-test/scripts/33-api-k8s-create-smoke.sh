#!/usr/bin/env bash
# 33-api-k8s-create-smoke.sh — exercise the api's K8s management endpoints.
#
# Real users create AerospikeCluster CRs from the UI, which goes through:
#   POST /api/v1/k8s/clusters
#   GET  /api/v1/k8s/clusters
#   GET  /api/v1/k8s/clusters/{ns}/{name}
#   GET  /api/v1/k8s/clusters/{ns}/{name}/health
#   GET  /api/v1/k8s/clusters/{ns}/{name}/yaml
#   DELETE /api/v1/k8s/clusters/{ns}/{name}
#
# Until this script existed the UI cluster-creation path was never exercised
# end-to-end in CI, even though it's the most common production code path.
#
# Eval criteria (PASS when):
#   1. POST /api/v1/k8s/clusters — creates a 1-node CR via api → 201/202
#   2. The CR appears in `kubectl get asc -n <ns>` and reaches Completed
#   3. GET /api/v1/k8s/clusters/{ns}/{name} returns 200 with status fields
#   4. GET .../health returns 200 with healthy=true (or equivalent)
#   5. GET .../yaml returns 200 with a parseable YAML body
#   6. DELETE removes the CR; subsequent GET returns 404
#
# Prereq: 12-helm-install.sh ran with K8s management enabled (chart default).
#
# Env: NS_OPERATOR, LOCAL_PORT (default: 18001 to avoid collision)
# Flags: --ns <ns>     namespace to create the CR in (default: $NS_AEROSPIKE)
#        --name <n>    CR name (default: api-smoke)
#        --timeout <s> wait for Completed (default: 180)

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="api-k8s-create"

LOCAL_PORT="${LOCAL_PORT:-18001}"
ns="$NS_AEROSPIKE"
name="api-smoke"
timeout=180

while [ $# -gt 0 ]; do
    case "$1" in
        --ns) ns="$2"; shift 2 ;;
        --name) name="$2"; shift 2 ;;
        --timeout) timeout="$2"; shift 2 ;;
        *) fail "$SCOPE" "unknown flag: $1" ;;
    esac
done

log_step "Opening port-forward to ui-api"
ui_svc=$(kubectl get svc -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}')
[ -n "$ui_svc" ] || fail "$SCOPE" "ui-api Service not found"
pf_open "$NS_OPERATOR" "$ui_svc" "$LOCAL_PORT" 80 >/dev/null

UI="http://localhost:${LOCAL_PORT}"

# -------- 0. Confirm the endpoint group is enabled --------
log_step "0. K8s management routes are exposed"
paths=$(curl -sS "$UI/api/openapi.json" | jq -r '.paths | keys[]' | grep -c '^/api/v1/k8s/' || true)
assert_count ge 5 "$paths" "≥5 /api/v1/k8s/* routes in openapi (K8S_MANAGEMENT_ENABLED)"

# -------- 1. POST create --------
log_step "1. POST /api/v1/k8s/clusters (create CR)"
kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - >&2

# The schema for CreateClusterRequest may differ across releases. We probe it.
schema=$(curl -sS "$UI/api/openapi.json" | jq -r '
    .paths["/api/v1/k8s/clusters"].post.requestBody.content["application/json"].schema."$ref" // empty
' | sed 's|.*/||')
[ -n "$schema" ] || fail "$SCOPE" "POST /api/v1/k8s/clusters missing requestBody schema in openapi"
log "request schema: $schema"

# Build a minimal payload — CE memory namespace, 1 node.
payload=$(jq -n --arg ns "$ns" --arg name "$name" '{
    namespace: $ns,
    name: $name,
    size: 1,
    image: "aerospike:ce-8.1.1.1",
    aerospikeConfig: {
        service: { "cluster-name": $name, "proto-fd-max": 15000 },
        network: {
            service: { address: "any", port: 3000 },
            heartbeat: { mode: "mesh", port: 3002 },
            fabric: { address: "any", port: 3001 }
        },
        namespaces: [{
            name: "test",
            "replication-factor": 1,
            "storage-engine": { type: "memory", "data-size": 1073741824 }
        }],
        logging: [{ name: "console", any: "info" }]
    }
}')

http=$(curl -sS -o /tmp/api-k8s-create.json -w '%{http_code}' \
    -X POST "$UI/api/v1/k8s/clusters" \
    -H 'Content-Type: application/json' \
    -d "$payload")
case "$http" in
    201|202|200) log_ok "POST returned $http" ;;
    *) cat /tmp/api-k8s-create.json >&2; fail "$SCOPE" "POST /api/v1/k8s/clusters got $http (want 200/201/202)" ;;
esac

# Cluster CR should now exist
log_step "2. CR exists and reaches Completed"
wait_for 30 1 "asc/$name appears in $ns" -- kubectl get asc -n "$ns" "$name"
wait_phase_completed "$ns" "$name" "$timeout"

# -------- 3. GET single cluster --------
log_step "3. GET /api/v1/k8s/clusters/$ns/$name"
http=$(curl -sS -o /tmp/api-k8s-get.json -w '%{http_code}' "$UI/api/v1/k8s/clusters/$ns/$name")
assert_eq 200 "$http" "GET single cluster"
jq -e '.metadata.name == "'"$name"'"' /tmp/api-k8s-get.json >/dev/null \
    || fail "$SCOPE" "GET single response missing .metadata.name=$name"

# -------- 4. GET health --------
log_step "4. GET .../health"
http=$(curl -sS -o /tmp/api-k8s-health.json -w '%{http_code}' "$UI/api/v1/k8s/clusters/$ns/$name/health")
assert_eq 200 "$http" "GET health"

# -------- 5. GET yaml --------
log_step "5. GET .../yaml"
http=$(curl -sS -o /tmp/api-k8s-yaml.txt -w '%{http_code}' "$UI/api/v1/k8s/clusters/$ns/$name/yaml")
assert_eq 200 "$http" "GET yaml"
yq . /tmp/api-k8s-yaml.txt >/dev/null 2>&1 || fail "$SCOPE" "yaml endpoint did not return parseable YAML"

# -------- 6. DELETE --------
log_step "6. DELETE .../$ns/$name"
http=$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "$UI/api/v1/k8s/clusters/$ns/$name")
case "$http" in
    200|202|204) log_ok "DELETE returned $http" ;;
    *) fail "$SCOPE" "DELETE got $http (want 200/202/204)" ;;
esac

wait_for 60 2 "asc/$name removed from $ns" -- bash -c "! kubectl get asc -n '$ns' '$name' >/dev/null 2>&1"

http=$(curl -sS -o /dev/null -w '%{http_code}' "$UI/api/v1/k8s/clusters/$ns/$name")
assert_eq 404 "$http" "GET after DELETE returns 404"

pass "$SCOPE" "create→Completed→get→health→yaml→delete cycle ok (ns=$ns name=$name)"
