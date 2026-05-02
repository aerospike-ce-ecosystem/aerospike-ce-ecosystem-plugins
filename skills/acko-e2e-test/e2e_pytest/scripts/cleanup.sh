#!/usr/bin/env bash
# cleanup.sh — best-effort teardown.
#
# Flags:
#   --kind        also delete the Kind cluster
#   --keep-cm     don't delete cert-manager (it's pricey to reinstall during dev)

source "$(dirname "$0")/_common.sh"

del_kind=0
keep_cm=0
for a in "$@"; do
    case "$a" in
        --kind) del_kind=1 ;;
        --keep-cm) keep_cm=1 ;;
    esac
done

if helm status "$HELM_RELEASE" -n "$NS_OPERATOR" >/dev/null 2>&1; then
    log "uninstalling helm release '$HELM_RELEASE'"
    helm uninstall "$HELM_RELEASE" -n "$NS_OPERATOR" --wait --timeout 2m >&2 || true
fi

namespaces_to_delete=("$NS_AEROSPIKE" "$NS_OTEL" "$NS_OPERATOR")
[ "$keep_cm" -eq 0 ] && namespaces_to_delete+=("cert-manager")
for ns in "${namespaces_to_delete[@]}"; do
    if kubectl get ns "$ns" >/dev/null 2>&1; then
        log "delete ns/$ns"
        kubectl delete ns "$ns" --ignore-not-found --wait=false >&2 || true
    fi
done

# Best-effort wait so a follow-up `helm install` doesn't trip on a still-Terminating ns.
deadline=$(( $(date +%s) + 60 ))
for ns in "${namespaces_to_delete[@]}"; do
    while kubectl get ns "$ns" >/dev/null 2>&1 && [ "$(date +%s)" -lt "$deadline" ]; do
        sleep 2
    done
done

if [ "$del_kind" -eq 1 ]; then
    log "deleting Kind cluster '$KIND_CLUSTER'"
    kind delete cluster --name "$KIND_CLUSTER" >&2 || true
fi

log "cleanup done"
