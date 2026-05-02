#!/usr/bin/env bash
# cert-manager.sh — install pinned cert-manager and wait for webhook readiness.
# Idempotent.

source "$(dirname "$0")/_common.sh"

if kubectl get deploy/cert-manager-webhook -n cert-manager >/dev/null 2>&1 \
    && kubectl wait deploy/cert-manager-webhook --for=condition=Available -n cert-manager --timeout=10s >/dev/null 2>&1; then
    log "cert-manager already healthy — reusing"
    exit 0
fi

log "Installing cert-manager $CERT_MANAGER_VERSION"
kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.yaml" >&2
kubectl wait deploy/cert-manager-webhook --for=condition=Available -n cert-manager --timeout=5m >&2

# webhook is "Available" before the CA finishes propagating — a follow-up
# `helm install` of the operator chart can race the CA otherwise.
sleep 10
log "cert-manager ready"
