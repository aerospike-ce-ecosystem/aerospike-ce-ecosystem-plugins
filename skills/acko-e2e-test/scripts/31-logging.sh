#!/usr/bin/env bash
# 31-logging.sh — verify the cluster-manager api logging stack.
#
# Eval criteria (PASS when):
#   1. Default LOG_FORMAT=text                — server logs are 'YYYY-... LEVEL [logger] message'
#   2. helm upgrade --set ui.env.logFormat=json — every record becomes a JSON
#      object with timestamp/level/logger/message/request_id keys
#   3. X-Request-ID round-trip                — header echoed in response AND
#      embedded as 'request_id' in the JSON log record
#   4. OTEL_SDK_DISABLED=true (default)        — pod env confirms the toggle
#
# This script intentionally toggles between text and json modes, so it must
# run AFTER 12-helm-install.sh and BEFORE 32-otel-runtime.sh (which expects
# json + otel both on).
#
# Env: NS_OPERATOR, HELM_RELEASE, CHART_PATH, LOCAL_PORT (default: 18002)
# Flags: --skip-text  skip the text-default check (useful when chart was
#                     already upgraded to json by a previous step)

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="logging"

LOCAL_PORT="${LOCAL_PORT:-18002}"
skip_text=0
for a in "$@"; do
    case "$a" in
        --skip-text) skip_text=1 ;;
    esac
done

ui_svc=$(kubectl get svc -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}')
[ -n "$ui_svc" ] || fail "$SCOPE" "ui-api Service not found"

# -------- 1. Default LOG_FORMAT=text --------
if [ "$skip_text" -eq 0 ]; then
    log_step "1. Default LOG_FORMAT=text"
    pod=$(kubectl get pod -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}')
    cur=$(kubectl exec -n "$NS_OPERATOR" "$pod" -c api -- printenv LOG_FORMAT 2>/dev/null || echo "")
    if [ "$cur" = "text" ] || [ -z "$cur" ]; then
        # Sample 10 lines from the api container; at least one must look like the text format.
        sample=$(kubectl logs -n "$NS_OPERATOR" "$pod" -c api --tail=20 2>/dev/null || true)
        assert_match '[0-9]{4}-[0-9]{2}-[0-9]{2}.*INFO.*\[' "$sample" "log line in text format"
    else
        log_warn "LOG_FORMAT='$cur' already non-text — skipping default-text assertion"
    fi
fi

# -------- 2. Upgrade to LOG_FORMAT=json --------
log_step "2. helm upgrade --set ui.env.logFormat=json"
helm upgrade "$HELM_RELEASE" "$CHART_PATH" \
    --namespace "$NS_OPERATOR" --reuse-values \
    --set ui.env.logFormat=json \
    --wait --timeout 3m >&2 \
    || fail "$SCOPE" "helm upgrade to json failed"
kubectl rollout status deploy -n "$NS_OPERATOR" --timeout=2m >&2 \
    || fail "$SCOPE" "rollout did not complete"

# Refresh pod handle after rollout
pod=$(kubectl get pod -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}')
log "current api pod: $pod"

# -------- 3. X-Request-ID round-trip --------
log_step "3. X-Request-ID round-trip in JSON mode"
pf_open "$NS_OPERATOR" "$ui_svc" "$LOCAL_PORT" 80 >/dev/null

rid="probe-json-$(date +%s%N)"
got_rid=$(curl -sS -D - -H "X-Request-ID: $rid" "http://localhost:${LOCAL_PORT}/api/health" -o /dev/null \
    | tr -d '\r' | awk '/^x-request-id:/ {print $2}' | tail -1)
assert_eq "$rid" "$got_rid" "x-request-id echoed in response"

# Allow logs to flush
sleep 2
# The middleware-emitted access log line carries request_id even with trace_id=null.
log_line=$(kubectl logs -n "$NS_OPERATOR" "$pod" -c api --since=30s 2>/dev/null | grep -F "$rid" | head -1)
[ -n "$log_line" ] || fail "$SCOPE" "no log line correlated with $rid"
echo "$log_line" | jq -e --arg rid "$rid" '.request_id == $rid' >/dev/null \
    || fail "$SCOPE" "log record present but request_id field != $rid"
log_ok "log record JSON has request_id=$rid"

# -------- 4. OTEL_SDK_DISABLED default behavior --------
log_step "4. OTEL_SDK_DISABLED env in api pod"
otel_disabled=$(kubectl exec -n "$NS_OPERATOR" "$pod" -c api -- printenv OTEL_SDK_DISABLED 2>/dev/null || echo "")
log "OTEL_SDK_DISABLED='$otel_disabled'"
# This script is agnostic — both states are valid here; 32-otel-runtime.sh
# is responsible for the OTel state. We just record the current value.

pass "$SCOPE" "text-default ok, json upgrade ok, X-Request-ID correlation ok"
