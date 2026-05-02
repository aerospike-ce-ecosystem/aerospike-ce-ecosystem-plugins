#!/usr/bin/env bash
# helm-install.sh — install (or upgrade) the operator chart with parametric overrides.
#
# Flags:
#   --release <name>        default: $HELM_RELEASE
#   --namespace <ns>        default: $NS_OPERATOR
#   --image-repo <repo>     default: $IMG repo part
#   --image-tag <tag>       default: $IMG tag part
#   --pull-policy <policy>  default: Never
#   --api-image-repo <repo> default: $API_IMG repo part
#   --api-image-tag <tag>   default: $API_IMG tag part
#   --log-format <fmt>      text|json (default: text)
#   --otel <on|off>         default: off
#   --otel-endpoint <url>   default: http://otel-collector.$NS_OTEL.svc.cluster.local:4317
#   --upgrade               run `helm upgrade --reuse-values` instead of install
#   --set <k=v>             repeatable: extra --set flag passthrough
#
# Output: just exits 0/1; orchestrator (pytest fixture) checks pod state.

source "$(dirname "$0")/_common.sh"

release="$HELM_RELEASE"
namespace="$NS_OPERATOR"
img_repo="${IMG%:*}"
img_tag="${IMG##*:}"
api_repo="${API_IMG%:*}"
api_tag="${API_IMG##*:}"
# Operator image is built locally and loaded into Kind → pullPolicy=Never.
# UI-api image is the upstream ghcr.io build → must be pullable, not Never.
pull_policy="Never"
api_pull_policy="IfNotPresent"
log_format="text"
otel="off"
otel_endpoint="http://otel-collector.${NS_OTEL}.svc.cluster.local:4317"
mode="install"
extras=()

while [ $# -gt 0 ]; do
    case "$1" in
        --release)          release="$2"; shift 2 ;;
        --namespace)        namespace="$2"; shift 2 ;;
        --image-repo)       img_repo="$2"; shift 2 ;;
        --image-tag)        img_tag="$2"; shift 2 ;;
        --pull-policy)      pull_policy="$2"; shift 2 ;;
        --api-image-repo)   api_repo="$2"; shift 2 ;;
        --api-image-tag)    api_tag="$2"; shift 2 ;;
        --api-pull-policy)  api_pull_policy="$2"; shift 2 ;;
        --log-format)       log_format="$2"; shift 2 ;;
        --otel)             otel="$2"; shift 2 ;;
        --otel-endpoint)    otel_endpoint="$2"; shift 2 ;;
        --upgrade)          mode="upgrade"; shift ;;
        --set)              extras+=("--set" "$2"); shift 2 ;;
        *) die "unknown flag: $1" ;;
    esac
done

[ -d "$CHART_PATH" ] || die "chart not found at $CHART_PATH"

set_args=(
    --set "image.repository=$img_repo"
    --set "image.tag=$img_tag"
    --set "image.pullPolicy=$pull_policy"
    --set "ui.api.image.repository=$api_repo"
    --set "ui.api.image.tag=$api_tag"
    --set "ui.api.image.pullPolicy=$api_pull_policy"
    --set "ui.env.logFormat=$log_format"
)

case "$otel" in
    on)
        set_args+=(--set "ui.api.otel.enabled=true")
        set_args+=(--set "ui.api.otel.endpoint=$otel_endpoint")
        set_args+=(--set "ui.api.otel.protocol=grpc")
        ;;
    off|"") ;;
    *) die "--otel must be on|off (got '$otel')" ;;
esac

set_args+=("${extras[@]+"${extras[@]}"}")

log "$mode helm release '$release' (operator=$img_repo:$img_tag api=$api_repo:$api_tag log=$log_format otel=$otel)"
case "$mode" in
    install)
        helm install "$release" "$CHART_PATH" \
            --namespace "$namespace" --create-namespace \
            "${set_args[@]}" \
            --wait --timeout 5m >&2
        ;;
    upgrade)
        helm upgrade "$release" "$CHART_PATH" \
            --namespace "$namespace" --reuse-values \
            "${set_args[@]}" \
            --wait --timeout 5m >&2
        ;;
esac

log "release ready"
