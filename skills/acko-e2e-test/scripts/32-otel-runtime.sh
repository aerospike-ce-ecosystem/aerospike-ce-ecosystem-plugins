#!/usr/bin/env bash
# 32-otel-runtime.sh — verify OTel opt-in actually exports spans end-to-end.
#
# This script is the regression guard for cluster-manager #265 — the
# FastAPIInstrumentor fix. Before that PR the env wiring was correct but
# zero spans reached the collector because FastAPI was never instrumented.
# If a future change reverts that, this script fails immediately.
#
# Eval criteria (PASS when):
#   1. Helm upgrade with ui.api.otel.enabled=true succeeds
#   2. OTEL_SDK_DISABLED=false + OTLP endpoint env in api pod
#   3. otel-collector deployed and Available
#   4. After traffic to /api/health + /api/v1/connections + /api/openapi.json,
#      the collector receives spans with service.name=aerospike-cluster-manager-api
#   5. Both instrumentation scopes appear:
#        - opentelemetry.instrumentation.fastapi  (HTTP server spans)
#        - opentelemetry.instrumentation.asyncpg  (DB client spans)
#   6. At least one trace contains BOTH a Server kind FastAPI span AND
#      an asyncpg child span sharing the trace ID — proving HTTP→DB context propagation.
#
# Env: NS_OPERATOR, NS_OTEL, HELM_RELEASE, CHART_PATH, LOCAL_PORT (default: 18003)
# Flags: --collector-image <ref>  override $COLLECTOR_IMAGE

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="otel-runtime"

LOCAL_PORT="${LOCAL_PORT:-18003}"

while [ $# -gt 0 ]; do
    case "$1" in
        --collector-image) COLLECTOR_IMAGE="$2"; shift 2 ;;
        *) fail "$SCOPE" "unknown flag: $1" ;;
    esac
done

ref_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../reference" && pwd)"
collector_yaml="$ref_dir/otel-collector.yaml"
[ -f "$collector_yaml" ] || fail "$SCOPE" "missing $collector_yaml"

# -------- 1+2. Upgrade with OTel enabled and verify env --------
log_step "1. helm upgrade with OTel enabled"
helm upgrade "$HELM_RELEASE" "$CHART_PATH" \
    --namespace "$NS_OPERATOR" --reuse-values \
    --set ui.env.logFormat=json \
    --set ui.api.otel.enabled=true \
    --set "ui.api.otel.endpoint=http://otel-collector.${NS_OTEL}.svc.cluster.local:4317" \
    --set ui.api.otel.protocol=grpc \
    --wait --timeout 3m >&2 \
    || fail "$SCOPE" "helm upgrade failed"

kubectl rollout status -n "$NS_OPERATOR" deploy --timeout=2m >&2 || fail "$SCOPE" "rollout did not finish"
pod=$(kubectl get pod -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}')
log "api pod: $pod"

log_step "2. Verifying OTEL_* env in api pod"
otel_env=$(kubectl exec -n "$NS_OPERATOR" "$pod" -c api -- printenv 2>/dev/null | grep '^OTEL_')
assert_match 'OTEL_SDK_DISABLED=false'         "$otel_env" "OTEL_SDK_DISABLED=false"
assert_match 'OTEL_EXPORTER_OTLP_ENDPOINT='   "$otel_env" "OTEL_EXPORTER_OTLP_ENDPOINT set"
assert_match 'OTEL_EXPORTER_OTLP_PROTOCOL=grpc' "$otel_env" "OTEL_EXPORTER_OTLP_PROTOCOL=grpc"
assert_match 'OTEL_SERVICE_NAME=aerospike-cluster-manager-api' "$otel_env" "OTEL_SERVICE_NAME"
assert_match 'OTEL_TRACES_SAMPLER='           "$otel_env" "OTEL_TRACES_SAMPLER set"

# -------- 3. Deploy collector --------
log_step "3. Deploying OTel collector"
kubectl apply -f "$collector_yaml" >&2 || fail "$SCOPE" "kubectl apply collector yaml failed"

# Hot-swap to a tag we can resolve. The yaml pins 0.115.0 historically; the
# collector floor is moving fast and the pinned tag is sometimes gone from
# docker.io. Try the latest tag we can pull locally.
if ! kubectl wait deploy/otel-collector --for=condition=Available -n "$NS_OTEL" --timeout=60s >/dev/null 2>&1; then
    log_warn "collector did not come up with the manifest's pinned image — patching to $COLLECTOR_IMAGE"
    "$CONTAINER_TOOL" pull "$COLLECTOR_IMAGE" >&2 || fail "$SCOPE" "failed to pull $COLLECTOR_IMAGE"
    "$CONTAINER_TOOL" save -o /tmp/otel-collector-image.tar "$COLLECTOR_IMAGE" >&2
    KIND_EXPERIMENTAL_PROVIDER="$KIND_PROVIDER" \
        kind load image-archive /tmp/otel-collector-image.tar --name "$KIND_CLUSTER" >&2
    rm -f /tmp/otel-collector-image.tar
    kubectl set image -n "$NS_OTEL" deploy/otel-collector "collector=$COLLECTOR_IMAGE" >&2
    kubectl patch deploy -n "$NS_OTEL" otel-collector --type='json' \
        -p='[{"op":"replace","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"Never"}]' >&2
    kubectl rollout status -n "$NS_OTEL" deploy/otel-collector --timeout=2m >&2 \
        || fail "$SCOPE" "collector did not become Ready after patch"
fi

# -------- 4. Generate traffic --------
log_step "4. Generating traffic"
ui_svc=$(kubectl get svc -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}')
pf_open "$NS_OPERATOR" "$ui_svc" "$LOCAL_PORT" 80 >/dev/null
for _ in 1 2 3 4 5; do
    curl -sS -o /dev/null "http://localhost:${LOCAL_PORT}/api/health"
    curl -sS -o /dev/null "http://localhost:${LOCAL_PORT}/api/v1/connections"
    curl -sS -o /dev/null "http://localhost:${LOCAL_PORT}/api/openapi.json"
done
log "15 requests sent — sleeping 8s for batch flush"
sleep 8

# -------- 5+6. Verify spans + parent/child propagation --------
log_step "5. Pulling collector logs"
clog=/tmp/otel-collector-spans.log
kubectl logs -n "$NS_OTEL" deploy/otel-collector --since=120s > "$clog" 2>&1 || fail "$SCOPE" "kubectl logs collector failed"

log_step "5a. service.name resource span"
grep -q 'service.name: Str(aerospike-cluster-manager-api)' "$clog" \
    || fail "$SCOPE" "no resource span with service.name=aerospike-cluster-manager-api"
log_ok "service.name=aerospike-cluster-manager-api seen"

log_step "5b. Both instrumentation scopes present"
grep -q 'InstrumentationScope opentelemetry.instrumentation.fastapi' "$clog" \
    || fail "$SCOPE" "no FastAPIInstrumentor scope (cluster-manager #265 may have regressed)"
grep -q 'InstrumentationScope opentelemetry.instrumentation.asyncpg' "$clog" \
    || fail "$SCOPE" "no AsyncPGInstrumentor scope"
log_ok "fastapi + asyncpg scopes both present"

log_step "6. Parent/child propagation (HTTP server → asyncpg client)"
# Find a server-kind FastAPI span (HTTP request) and check that at least one
# asyncpg child span carries the same trace ID.
server_traces=$(awk '
    /InstrumentationScope opentelemetry.instrumentation.fastapi/ { in_fastapi=1 }
    in_fastapi && /^Span #/ { in_span=1; trace=""; kind="" }
    in_span && /^[[:space:]]*Trace ID[[:space:]]*:/ { trace=$NF }
    in_span && /^[[:space:]]*Kind[[:space:]]*: Server/ { kind="Server" }
    in_span && /^$/ { if (kind=="Server") print trace; in_span=0 }
    /^InstrumentationScope/ && !/fastapi/ { in_fastapi=0 }
' "$clog" | sort -u)
[ -n "$server_traces" ] || fail "$SCOPE" "no Server-kind FastAPI span found (HTTP requests not instrumented)"
log "Server FastAPI traces: $(echo "$server_traces" | tr '\n' ' ')"

correlated=0
for tid in $server_traces; do
    asyncpg_child=$(awk -v tid="$tid" '
        /InstrumentationScope opentelemetry.instrumentation.asyncpg/ { in_pg=1 }
        in_pg && /^Span #/ { in_span=1; trace=""; parent="" }
        in_span && /^[[:space:]]*Trace ID[[:space:]]*:/ { trace=$NF }
        in_span && /^[[:space:]]*Parent ID[[:space:]]*:/ { parent=$NF }
        in_span && /^$/ { if (trace==tid && parent != "") print trace"|"parent; in_span=0 }
        /^InstrumentationScope/ && !/asyncpg/ { in_pg=0 }
    ' "$clog" | head -1)
    if [ -n "$asyncpg_child" ]; then
        log_ok "trace $tid has asyncpg child (parent=${asyncpg_child#*|})"
        correlated=$((correlated + 1))
    fi
done
assert_count ge 1 "$correlated" "≥1 trace contains both a FastAPI server span and an asyncpg child span"

pass "$SCOPE" "spans=$(grep -c '^Span #' "$clog") server-traces=$(echo "$server_traces" | wc -l | tr -d ' ') correlated=$correlated"
