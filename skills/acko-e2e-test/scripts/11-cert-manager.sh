#!/usr/bin/env bash
# 11-cert-manager.sh — install cert-manager (required by the operator chart's webhook).
#
# Eval criteria (PASS when):
#   - cert-manager-webhook deployment is Available
#   - extra 10s sleep after Available, since webhook CA propagation takes a beat
#
# Pinned to $CERT_MANAGER_VERSION matching test/utils/utils.go.
#
# Idempotent — if already installed, just waits for readiness.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="cert-manager"

if ns_exists cert-manager && deploy_ready cert-manager cert-manager-webhook; then
    log_ok "cert-manager already healthy — reusing"
    pass "$SCOPE" "version=$CERT_MANAGER_VERSION (reused)"
fi

log_step "Applying cert-manager $CERT_MANAGER_VERSION manifest"
kubectl apply -f "https://github.com/cert-manager/cert-manager/releases/download/${CERT_MANAGER_VERSION}/cert-manager.yaml" >&2 \
    || fail "$SCOPE" "kubectl apply failed"

log_step "Waiting for cert-manager-webhook Available"
kubectl wait deployment/cert-manager-webhook --for=condition=Available -n cert-manager --timeout=5m >&2 \
    || fail "$SCOPE" "webhook did not become Available within 5m"

log "Sleeping 10s for webhook CA propagation"
sleep 10

n_pods=$(kubectl get pods -n cert-manager --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
assert_count ge 3 "$n_pods" "expected ≥3 Running cert-manager pods (got $n_pods)"

pass "$SCOPE" "version=$CERT_MANAGER_VERSION pods=$n_pods"
