#!/usr/bin/env bash
# 60-diag-bundle.sh — capture a diagnostic bundle for a failing run.
#
# Always call BEFORE 99-cleanup.sh — once the namespaces are gone, half of
# this is unrecoverable. The orchestrator (run-all.sh) does this automatically
# on any e2e:fail line.
#
# Output: a directory under $BUNDLE_DIR (default: /tmp/e2e-diag-<timestamp>)
# containing:
#   * state.txt          — kubectl get pods,asc,statefulset,configmap,pvc,pdb -A -o wide
#   * describe-asc.txt   — kubectl describe asc -A
#   * operator.log       — operator pod logs (--tail=2000)
#   * api.log            — ui-api pod logs (--tail=2000)
#   * api-prev.log       — previous container logs (if any)
#   * events.txt         — kubectl get events -A --sort-by=lastTimestamp
#   * crd.yaml           — both ACKO CRDs
#   * webhook.yaml       — validating + mutating webhook configs
#   * helm-values.yaml   — current release values (if a release exists)
#   * collector.log      — last 200 lines (if otel namespace exists)
#
# Env: NS_OPERATOR, NS_OTEL, HELM_RELEASE, BUNDLE_DIR

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="diag-bundle"

BUNDLE_DIR="${BUNDLE_DIR:-/tmp/e2e-diag-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$BUNDLE_DIR"

log_step "Capturing cluster state into $BUNDLE_DIR"

kubectl get pods,asc,statefulset,configmap,pvc,pdb -A -o wide > "$BUNDLE_DIR/state.txt" 2>&1 || true
kubectl describe asc -A > "$BUNDLE_DIR/describe-asc.txt" 2>&1 || true
kubectl get events -A --sort-by='.lastTimestamp' > "$BUNDLE_DIR/events.txt" 2>&1 || true

# Operator logs
op_pod=$(kubectl get pod -n "$NS_OPERATOR" -l control-plane=controller-manager -o name 2>/dev/null | head -1 || true)
if [ -n "$op_pod" ]; then
    kubectl logs -n "$NS_OPERATOR" "$op_pod" --tail=2000 > "$BUNDLE_DIR/operator.log" 2>&1 || true
fi

# API + UI logs
api_pod=$(kubectl get pod -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -n "$api_pod" ]; then
    kubectl logs -n "$NS_OPERATOR" "$api_pod" -c api --tail=2000 > "$BUNDLE_DIR/api.log" 2>&1 || true
    kubectl logs -n "$NS_OPERATOR" "$api_pod" -c api --tail=2000 --previous > "$BUNDLE_DIR/api-prev.log" 2>&1 || true
fi

# CRDs + webhook configs
for crd in aerospikeclusters.acko.io aerospikeclustertemplates.acko.io; do
    kubectl get crd "$crd" -o yaml >> "$BUNDLE_DIR/crd.yaml" 2>&1 || true
done
kubectl get validatingwebhookconfiguration -o yaml > "$BUNDLE_DIR/webhook.yaml" 2>&1 || true
kubectl get mutatingwebhookconfiguration -o yaml >> "$BUNDLE_DIR/webhook.yaml" 2>&1 || true

# Helm values
if helm status "$HELM_RELEASE" -n "$NS_OPERATOR" >/dev/null 2>&1; then
    helm get values "$HELM_RELEASE" -n "$NS_OPERATOR" > "$BUNDLE_DIR/helm-values.yaml" 2>&1 || true
    helm get manifest "$HELM_RELEASE" -n "$NS_OPERATOR" > "$BUNDLE_DIR/helm-manifest.yaml" 2>&1 || true
fi

# Collector logs
if ns_exists "$NS_OTEL"; then
    kubectl logs -n "$NS_OTEL" deploy/otel-collector --tail=200 > "$BUNDLE_DIR/collector.log" 2>&1 || true
fi

n_files=$(find "$BUNDLE_DIR" -type f | wc -l | tr -d ' ')
log_ok "captured $n_files files"
pass "$SCOPE" "bundle=$BUNDLE_DIR files=$n_files"
