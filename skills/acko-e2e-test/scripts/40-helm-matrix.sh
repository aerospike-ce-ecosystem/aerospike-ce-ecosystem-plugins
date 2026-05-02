#!/usr/bin/env bash
# 40-helm-matrix.sh — chart lint + 7-mode helm template assertion matrix.
#
# Eval criteria (PASS when all 7 modes render or fail-fast as expected):
#   M1 operator-only (--set ui.enabled=false)
#       → Operator Deployment present, NO ui-api/ui-web Deployment, NO ServiceMonitor.
#   M2 UI full (api+web)
#       → operator+api+web Deployments, NetworkPolicy with both :8000 and :3100,
#         helm-test pod present.
#   M3 UI api-only (ui.web.enabled=false, ingress.target=api)
#       → operator+api Deployments only, NetworkPolicy with ONLY :8000,
#         helm-test pod present.
#   M4 UI web-only (ui.api.enabled=false)
#       → operator+web Deployments only, NetworkPolicy with ONLY :3100,
#         web pod has automountServiceAccountToken=false, NO helm-test pod.
#   M5 OTel disabled (default)
#       → api env contains OTEL_SDK_DISABLED=true, no OTLP endpoint.
#   M6 OTel enabled (ui.api.otel.enabled=true,endpoint=...)
#       → api env contains OTEL_SDK_DISABLED=false, OTEL_EXPORTER_OTLP_ENDPOINT,
#         OTEL_TRACES_SAMPLER, OTEL_SERVICE_NAME.
#   M7 ingress.target failfast
#       → helm template MUST FAIL with a clear error.
#
# This script does NOT need a Kind cluster — only `helm` + `yq`. Useful as
# a fast PR gate.
#
# Env: CHART_PATH (must point to charts/aerospike-ce-kubernetes-operator)

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="helm-matrix"
require_chart
require_tool helm
require_tool yq

# ---- helm lint ----
log_step "helm lint"
out=$(helm lint "$CHART_PATH" 2>&1) || fail "$SCOPE" "helm lint failed: $out"
log_ok "helm lint clean"

render() {
    # render <out_file> <set_args...>
    local out="$1"; shift
    helm template foo "$CHART_PATH" "$@" > "$out" 2>&1
}

# yq emits one document per match plus '---' separators; awk strips both
# blank and '---' lines without erroring on empty input (which `grep -v` would
# under `set -o pipefail`).
strip_yaml_noise() { awk 'NF && $0 != "---"'; }

deploy_names() {
    yq -r 'select(.kind == "Deployment") | .metadata.name' "$1" | strip_yaml_noise
}

helm_test_count() {
    yq -r 'select(.kind == "Pod" and .metadata.annotations["helm.sh/hook"] == "test") | .metadata.name' "$1" \
        | strip_yaml_noise | wc -l | tr -d ' '
}

np_ports() {
    yq -r 'select(.kind == "NetworkPolicy") | .spec.ingress[]?.ports[]?.port' "$1" \
        | strip_yaml_noise | sort -u
}

api_env_value() {
    # api_env_value <out_file> <ENV_NAME>
    yq -r '
        select(.kind == "Deployment" and .metadata.name == "foo-aerospike-ce-kubernetes-operator-ui-api")
        | .spec.template.spec.containers[]
        | select(.name == "api")
        | .env[]
        | select(.name == "'"$2"'")
        | .value
    ' "$1" 2>/dev/null | head -1
}

# ---- M1: operator-only ----
log_step "M1: operator-only (--set ui.enabled=false)"
m1=/tmp/m1-operator-only.yaml
render "$m1" --set ui.enabled=false || fail "$SCOPE" "M1 helm template failed"
deploys=$(deploy_names "$m1")
echo "$deploys" | grep -qx 'foo-aerospike-ce-kubernetes-operator' || fail "$SCOPE" "M1 operator Deployment missing"
echo "$deploys" | grep -q 'ui-api\|ui-web' && fail "$SCOPE" "M1 should have no UI Deployments, got: $deploys"
yq -r 'select(.kind == "ServiceMonitor")' "$m1" | grep -q . && fail "$SCOPE" "M1 should have no ServiceMonitor"
log_ok "M1 ok"

# ---- M2: UI full ----
log_step "M2: UI full (api + web + NetworkPolicy + helm-test)"
m2=/tmp/m2-ui-full.yaml
render "$m2" --set ui.enabled=true --set ui.networkPolicy.enabled=true --set ui.tests.enabled=true \
    || fail "$SCOPE" "M2 helm template failed"
deploys=$(deploy_names "$m2")
echo "$deploys" | grep -qx 'foo-aerospike-ce-kubernetes-operator-ui-api' || fail "$SCOPE" "M2 ui-api missing"
echo "$deploys" | grep -qx 'foo-aerospike-ce-kubernetes-operator-ui-web' || fail "$SCOPE" "M2 ui-web missing"
ports=$(np_ports "$m2")
echo "$ports" | grep -qx 8000 || fail "$SCOPE" "M2 NetworkPolicy missing :8000 (got: $ports)"
echo "$ports" | grep -qx 3100 || fail "$SCOPE" "M2 NetworkPolicy missing :3100 (got: $ports)"
n_test=$(helm_test_count "$m2")
assert_count ge 1 "$n_test" "M2 helm-test pod count"
log_ok "M2 ok"

# ---- M3: UI api-only ----
log_step "M3: UI api-only"
m3=/tmp/m3-ui-api-only.yaml
render "$m3" --set ui.enabled=true --set ui.web.enabled=false --set ui.ingress.target=api \
    --set ui.networkPolicy.enabled=true --set ui.tests.enabled=true \
    || fail "$SCOPE" "M3 helm template failed"
deploys=$(deploy_names "$m3")
echo "$deploys" | grep -qx 'foo-aerospike-ce-kubernetes-operator-ui-api' || fail "$SCOPE" "M3 ui-api missing"
echo "$deploys" | grep -q 'ui-web' && fail "$SCOPE" "M3 should have no ui-web Deployment"
ports=$(np_ports "$m3")
echo "$ports" | grep -qx 8000 || fail "$SCOPE" "M3 NetworkPolicy missing :8000"
echo "$ports" | grep -qx 3100 && fail "$SCOPE" "M3 NetworkPolicy must NOT contain :3100 (got: $ports)"
log_ok "M3 ok"

# ---- M4: UI web-only ----
log_step "M4: UI web-only"
m4=/tmp/m4-ui-web-only.yaml
render "$m4" --set ui.enabled=true --set ui.api.enabled=false --set ui.web.env.apiUrl=http://x \
    --set ui.networkPolicy.enabled=true --set ui.tests.enabled=true \
    || fail "$SCOPE" "M4 helm template failed"
deploys=$(deploy_names "$m4")
echo "$deploys" | grep -qx 'foo-aerospike-ce-kubernetes-operator-ui-web' || fail "$SCOPE" "M4 ui-web missing"
echo "$deploys" | grep -q 'ui-api' && fail "$SCOPE" "M4 should have no ui-api Deployment"
ports=$(np_ports "$m4")
echo "$ports" | grep -qx 3100 || fail "$SCOPE" "M4 NetworkPolicy missing :3100"
echo "$ports" | grep -qx 8000 && fail "$SCOPE" "M4 NetworkPolicy must NOT contain :8000"
amst=$(yq -r 'select(.kind == "Deployment" and .metadata.name == "foo-aerospike-ce-kubernetes-operator-ui-web") | .spec.template.spec.automountServiceAccountToken' "$m4" | head -1)
assert_eq "false" "$amst" "M4 ui-web automountServiceAccountToken=false"
n_test=$(helm_test_count "$m4")
assert_count eq 0 "$n_test" "M4 helm-test pod count (api disabled → no test pod)"
log_ok "M4 ok"

# ---- M5: OTel disabled (default) ----
log_step "M5: OTel disabled (default)"
m5=/tmp/m5-otel-default.yaml
render "$m5" --set ui.enabled=true || fail "$SCOPE" "M5 helm template failed"
val=$(api_env_value "$m5" OTEL_SDK_DISABLED)
assert_eq "true" "$val" "M5 OTEL_SDK_DISABLED env"
val=$(api_env_value "$m5" OTEL_EXPORTER_OTLP_ENDPOINT)
[ -z "$val" ] || fail "$SCOPE" "M5 should not set OTEL_EXPORTER_OTLP_ENDPOINT (got '$val')"
log_ok "M5 ok"

# ---- M6: OTel enabled ----
log_step "M6: OTel enabled"
m6=/tmp/m6-otel-enabled.yaml
render "$m6" --set ui.enabled=true --set ui.api.otel.enabled=true \
    --set ui.api.otel.endpoint=http://col:4317 \
    || fail "$SCOPE" "M6 helm template failed"
assert_eq "false" "$(api_env_value "$m6" OTEL_SDK_DISABLED)"            "M6 OTEL_SDK_DISABLED"
assert_eq "http://col:4317" "$(api_env_value "$m6" OTEL_EXPORTER_OTLP_ENDPOINT)" "M6 OTEL_EXPORTER_OTLP_ENDPOINT"
[ -n "$(api_env_value "$m6" OTEL_TRACES_SAMPLER)" ] || fail "$SCOPE" "M6 OTEL_TRACES_SAMPLER not set"
[ -n "$(api_env_value "$m6" OTEL_SERVICE_NAME)" ]    || fail "$SCOPE" "M6 OTEL_SERVICE_NAME not set"
log_ok "M6 ok"

# ---- M7: ingress.target failfast ----
log_step "M7: ingress.target failfast (must FAIL)"
m7=/tmp/m7-failfast.yaml
if helm template foo "$CHART_PATH" \
    --set ui.enabled=true --set ui.web.enabled=false --set ui.ingress.enabled=true \
    > "$m7" 2>&1; then
    fail "$SCOPE" "M7 helm template should have failed but succeeded"
fi
grep -qE 'ui\.ingress\.target' "$m7" \
    || fail "$SCOPE" "M7 failed but error did not mention ui.ingress.target"
log_ok "M7 fails as documented"

pass "$SCOPE" "lint clean + 7/7 modes verified"
