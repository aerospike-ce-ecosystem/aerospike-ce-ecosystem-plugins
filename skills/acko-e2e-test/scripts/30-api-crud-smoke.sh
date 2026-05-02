#!/usr/bin/env bash
# 30-api-crud-smoke.sh — exercise the cluster-manager UI api against a live
# Aerospike cluster. Re-runs the four 500-error fixes from cluster-manager
# #261 against the real binary every release.
#
# Prerequisites:
#   - 12-helm-install.sh succeeded (api pod Running)
#   - 21-asc-create-smoke.sh ran with --keep, so an asc named '$ASC_NAME'
#     in '$NS_AEROSPIKE' is in phase=Completed
#
# Eval criteria (PASS when all of):
#   A. Connection lifecycle  : POST 201 + id, GET list contains it,
#                              DELETE 204, GET 404 afterwards
#   B. Cluster reachability  : GET /api/v1/clusters/{conn_id} 200 with
#                              namespaces[].name including 'test'
#   C. sample-data #257       : POST 201 with recordsCreated, recordsFailed,
#                              indexesCreated, indexesFailed in body
#                              (NEVER 500 even if some indexes fail)
#   D. records empty #259    : GET ?ns=test&set=does-not-exist&pageSize=3
#                              200 with records:[]  (NOT 500)
#   E. query pkType=auto #258: POST {pkType:'auto'} 200, behaves like default
#   F. indexes idempotency #260: POST 201 (state:building) → DELETE 204 →
#                                DELETE-again 204 (no 500 on already-deleted)
#   G. X-Request-ID header   : every response carries x-request-id
#
# Env: NS_OPERATOR, NS_AEROSPIKE, ASC_NAME (default: aerospike-basic),
#      LOCAL_PORT (default: 18000)

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="api-crud"

ASC_NAME="${ASC_NAME:-aerospike-basic}"
LOCAL_PORT="${LOCAL_PORT:-18000}"

# Sanity check the prereqs before opening a port-forward.
phase=$(kubectl get asc -n "$NS_AEROSPIKE" "$ASC_NAME" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
[ "$phase" = "Completed" ] || fail "$SCOPE" "asc/$ASC_NAME not Completed (run 21-asc-create-smoke.sh --keep first; phase='$phase')"

log_step "Opening port-forward to ui-api"
ui_svc=$(kubectl get svc -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}')
[ -n "$ui_svc" ] || fail "$SCOPE" "ui-api Service not found"
pf_open "$NS_OPERATOR" "$ui_svc" "$LOCAL_PORT" 80 >/dev/null

UI="http://localhost:${LOCAL_PORT}"
SEED=$(asc_seed_host "$ASC_NAME" "$NS_AEROSPIKE")

# -------- A. Connection lifecycle --------
log_step "A. Connection lifecycle"
http=$(curl -sS -o /tmp/api-conn.json -w '%{http_code}' \
    -X POST "$UI/api/v1/connections" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"smoke\",\"hosts\":[\"$SEED\"],\"port\":3000}")
assert_eq 201 "$http" "POST /api/v1/connections"
conn_id=$(jq -r '.id' /tmp/api-conn.json)
[ -n "$conn_id" ] && [ "$conn_id" != "null" ] || fail "$SCOPE" "no id in connection response"
log_ok "created connection id=$conn_id"

curl -sS "$UI/api/v1/connections" | jq -e --arg id "$conn_id" 'map(.id) | index($id) != null' >/dev/null \
    || fail "$SCOPE" "GET list does not contain $conn_id"
log_ok "GET list contains $conn_id"

# -------- B. Cluster reachability --------
log_step "B. Cluster reachability"
http=$(curl -sS -o /tmp/api-cluster.json -w '%{http_code}' "$UI/api/v1/clusters/$conn_id")
assert_eq 200 "$http" "GET /api/v1/clusters/$conn_id"
ns_names=$(jq -r '.namespaces[].name' /tmp/api-cluster.json | tr '\n' ',')
assert_match 'test' "$ns_names" "namespace 'test' visible in cluster ns list"

# -------- C. sample-data #257 --------
log_step "C. sample-data partial-success contract (#257)"
http=$(curl -sS -o /tmp/api-sample.json -w '%{http_code}' \
    -X POST "$UI/api/v1/sample-data/$conn_id" \
    -H 'Content-Type: application/json' \
    -d '{"namespace":"test","setName":"smoke30","recordCount":10}')
assert_eq 201 "$http" "POST /api/v1/sample-data (success path)"
for k in recordsCreated recordsFailed indexesCreated indexesFailed; do
    jq -e "has(\"$k\")" /tmp/api-sample.json >/dev/null || fail "$SCOPE" "sample-data response missing '$k'"
done
log_ok "response body has recordsCreated/Failed + indexesCreated/Failed"

# Force partial failure to confirm we still get 201 (NOT 500).
http=$(curl -sS -o /tmp/api-sample-bad.json -w '%{http_code}' \
    -X POST "$UI/api/v1/sample-data/$conn_id" \
    -H 'Content-Type: application/json' \
    -d '{"namespace":"this-ns-does-not-exist-XYZ","setName":"smoke30","recordCount":1}')
assert_eq 201 "$http" "POST /api/v1/sample-data (bad-ns must be 201 partial-success, NEVER 500)"
fail_count=$(jq -r '.recordsFailed // 0' /tmp/api-sample-bad.json)
assert_count ge 1 "$fail_count" "bad-ns case reports recordsFailed≥1"

# -------- D. records empty/sparse #259 --------
log_step "D. records empty set (#259)"
http=$(curl -sS -o /tmp/api-records.json -w '%{http_code}' \
    "$UI/api/v1/records/$conn_id?ns=test&set=does-not-exist&pageSize=3")
assert_eq 200 "$http" "GET /api/v1/records (empty set)"
records_len=$(jq '.records | length' /tmp/api-records.json)
assert_eq 0 "$records_len" "records:[] for non-existent set"

# -------- E. query pkType=auto #258 --------
log_step "E. query pkType=auto (#258)"
http=$(curl -sS -o /tmp/api-query.json -w '%{http_code}' \
    -X POST "$UI/api/v1/query/$conn_id" \
    -H 'Content-Type: application/json' \
    -d '{"namespace":"test","maxRecords":3,"pkType":"auto"}')
assert_eq 200 "$http" "POST /api/v1/query (pkType=auto)"
jq -e '.records | type == "array"' /tmp/api-query.json >/dev/null \
    || fail "$SCOPE" "query response has no .records array"

# -------- F. indexes idempotency #260 --------
log_step "F. indexes idempotency (#260)"
http=$(curl -sS -o /tmp/api-idx-create.json -w '%{http_code}' \
    -X POST "$UI/api/v1/indexes/$conn_id" \
    -H 'Content-Type: application/json' \
    -d '{"namespace":"test","set":"smoke30","name":"idx_smoke30_int","bin":"bin_int","type":"numeric"}')
assert_eq 201 "$http" "POST /api/v1/indexes (create)"
state=$(jq -r '.state' /tmp/api-idx-create.json)
assert_match 'building|ready' "$state" "index state ∈ {building, ready}"

http=$(curl -sS -o /dev/null -w '%{http_code}' \
    -X DELETE "$UI/api/v1/indexes/$conn_id?name=idx_smoke30_int&ns=test")
assert_eq 204 "$http" "DELETE /api/v1/indexes (first call)"

http=$(curl -sS -o /dev/null -w '%{http_code}' \
    -X DELETE "$UI/api/v1/indexes/$conn_id?name=idx_smoke30_int&ns=test")
assert_eq 204 "$http" "DELETE /api/v1/indexes (idempotent — same as first)"

# -------- G. X-Request-ID round-trip --------
log_step "G. X-Request-ID header always present"
rid="probe-$(date +%s%N)"
got_rid=$(curl -sS -D - -H "X-Request-ID: $rid" "$UI/api/v1/connections" -o /dev/null \
    | tr -d '\r' | awk '/^x-request-id:/ {print $2}' | tail -1)
assert_eq "$rid" "$got_rid" "x-request-id echoed back unchanged"

# -------- A2. Close out the connection lifecycle --------
log_step "A2. Closing connection"
http=$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE "$UI/api/v1/connections/$conn_id")
assert_eq 204 "$http" "DELETE /api/v1/connections/$conn_id"
http=$(curl -sS -o /dev/null -w '%{http_code}' "$UI/api/v1/connections/$conn_id")
assert_eq 404 "$http" "GET /api/v1/connections/$conn_id (after delete)"

pass "$SCOPE" "7 contracts verified (A–G) against asc/$ASC_NAME"
