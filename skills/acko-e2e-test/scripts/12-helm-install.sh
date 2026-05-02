#!/usr/bin/env bash
# 12-helm-install.sh — parametric helm install/upgrade of the operator chart.
#
# Eval criteria (PASS when):
#   - helm release '$HELM_RELEASE' STATUS=deployed in $NS_OPERATOR
#   - operator + (optionally) ui-api + ui-web Deployments are Available
#   - both AerospikeCluster CRDs are present
#
# Flags (all optional):
#   --image <repo>     operator image repo (default: $IMG repo part)
#   --tag <tag>        operator image tag (default: $IMG tag part)
#   --pull-policy <p>  default: Never (we always pre-load)
#   --api-image <repo> override ui-api image (e.g. for testing a patched build)
#   --api-tag <tag>
#   --log-format <fmt> text | json (default: text)
#   --otel <on|off>    enable OTel (sets endpoint to in-cluster collector)
#   --otel-endpoint <url>  default: http://otel-collector.otel.svc.cluster.local:4317
#   --upgrade          run `helm upgrade --reuse-values` instead of install
#   --extra <kv>       repeatable: passes --set <kv> through to helm
#
# Env: HELM_RELEASE, NS_OPERATOR, IMG, API_IMG, CHART_PATH

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="helm-install"
require_chart

img_repo="${IMG%:*}"
img_tag="${IMG##*:}"
api_repo="${API_IMG%:*}"
api_tag="${API_IMG##*:}"
pull_policy="Never"
log_format="text"
otel="off"
otel_endpoint="http://otel-collector.${NS_OTEL}.svc.cluster.local:4317"
mode="install"
extras=()

while [ $# -gt 0 ]; do
    case "$1" in
        --image)        img_repo="$2"; shift 2 ;;
        --tag)          img_tag="$2"; shift 2 ;;
        --pull-policy)  pull_policy="$2"; shift 2 ;;
        --api-image)    api_repo="$2"; shift 2 ;;
        --api-tag)      api_tag="$2"; shift 2 ;;
        --log-format)   log_format="$2"; shift 2 ;;
        --otel)         otel="$2"; shift 2 ;;
        --otel-endpoint) otel_endpoint="$2"; shift 2 ;;
        --upgrade)      mode="upgrade"; shift ;;
        --extra)        extras+=("--set" "$2"); shift 2 ;;
        *) fail "$SCOPE" "unknown flag: $1" ;;
    esac
done

set_args=(
    --set "image.repository=$img_repo"
    --set "image.tag=$img_tag"
    --set "image.pullPolicy=$pull_policy"
    --set "ui.api.image.repository=$api_repo"
    --set "ui.api.image.tag=$api_tag"
    --set "ui.api.image.pullPolicy=$pull_policy"
    --set "ui.env.logFormat=$log_format"
)

case "$otel" in
    on)
        set_args+=(--set "ui.api.otel.enabled=true")
        set_args+=(--set "ui.api.otel.endpoint=$otel_endpoint")
        set_args+=(--set "ui.api.otel.protocol=grpc")
        ;;
    off|"") ;;
    *) fail "$SCOPE" "--otel must be on|off, got '$otel'" ;;
esac

set_args+=("${extras[@]}")

log_step "$mode helm release '$HELM_RELEASE' (operator=$img_repo:$img_tag api=$api_repo:$api_tag log=$log_format otel=$otel)"
case "$mode" in
    install)
        helm install "$HELM_RELEASE" "$CHART_PATH" \
            --namespace "$NS_OPERATOR" --create-namespace \
            "${set_args[@]}" \
            --wait --timeout 5m >&2 \
            || fail "$SCOPE" "helm install failed"
        ;;
    upgrade)
        helm upgrade "$HELM_RELEASE" "$CHART_PATH" \
            --namespace "$NS_OPERATOR" --reuse-values \
            "${set_args[@]}" \
            --wait --timeout 5m >&2 \
            || fail "$SCOPE" "helm upgrade failed"
        ;;
esac

log_step "Verifying release state"
status=$(helm status "$HELM_RELEASE" -n "$NS_OPERATOR" -o json 2>/dev/null | yq -r .info.status)
assert_eq "deployed" "$status" "helm release status"

# Wait for the rollouts
kubectl rollout status -n "$NS_OPERATOR" deploy --timeout=3m >&2 || fail "$SCOPE" "deploy rollout did not finish"

# CRDs
for crd in aerospikeclusters.acko.io aerospikeclustertemplates.acko.io; do
    kubectl get crd "$crd" >/dev/null 2>&1 || fail "$SCOPE" "CRD $crd missing"
    log_ok "CRD $crd present"
done

n_running=$(kubectl get pods -n "$NS_OPERATOR" --field-selector=status.phase=Running --no-headers | wc -l | tr -d ' ')
pass "$SCOPE" "release=$HELM_RELEASE mode=$mode pods=$n_running otel=$otel"
