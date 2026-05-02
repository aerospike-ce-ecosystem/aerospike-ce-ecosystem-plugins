#!/usr/bin/env bash
# 99-cleanup.sh — tear down everything an e2e run created.
#
# Steps:
#   1. helm uninstall release (if exists)
#   2. delete ns aerospike, otel, cert-manager, aerospike-operator
#   3. (optional) kind delete cluster — only when --kind is passed
#
# Env: KIND_CLUSTER, NS_OPERATOR, NS_AEROSPIKE, NS_OTEL, HELM_RELEASE
# Flags: --kind  → also delete the Kind cluster
# Exit: 0 (cleanup is best-effort; a missing resource is not a failure)

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="cleanup"

KILL_KIND=0
for a in "$@"; do
    case "$a" in
        --kind) KILL_KIND=1 ;;
    esac
done

log_step "Uninstalling helm release if present"
if helm status "$HELM_RELEASE" -n "$NS_OPERATOR" >/dev/null 2>&1; then
    helm uninstall "$HELM_RELEASE" -n "$NS_OPERATOR" --wait --timeout 2m >&2 || true
    log_ok "helm release '$HELM_RELEASE' uninstalled"
else
    log "no helm release '$HELM_RELEASE' in $NS_OPERATOR"
fi

log_step "Deleting test namespaces"
for ns in "$NS_AEROSPIKE" "$NS_OTEL" "$NS_OPERATOR" cert-manager; do
    if ns_exists "$ns"; then
        kubectl delete ns "$ns" --ignore-not-found --wait=false >&2 || true
        log_ok "delete ns/$ns scheduled"
    fi
done

# Best-effort wait so a follow-up `helm install` doesn't trip on a still-Terminating ns.
for ns in "$NS_AEROSPIKE" "$NS_OTEL" "$NS_OPERATOR" cert-manager; do
    deadline=$(( $(date +%s) + 60 ))
    while ns_exists "$ns" && [ "$(date +%s)" -lt "$deadline" ]; do
        sleep 2
    done
done

if [ "$KILL_KIND" -eq 1 ]; then
    log_step "Deleting Kind cluster '$KIND_CLUSTER'"
    kind delete cluster --name "$KIND_CLUSTER" >&2 || true
    pass "$SCOPE" "namespaces removed, Kind cluster '$KIND_CLUSTER' deleted"
fi

pass "$SCOPE" "namespaces removed (Kind cluster preserved — pass --kind to also delete)"
