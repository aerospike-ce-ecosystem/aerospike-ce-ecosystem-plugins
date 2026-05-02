#!/usr/bin/env bash
# diag-bundle.sh — capture cluster state + logs for failure post-mortem.
# Called by conftest.py's failure hook before any teardown runs.
#
# Output: $BUNDLE_DIR (default: /tmp/e2e-diag-<timestamp>)

source "$(dirname "$0")/_common.sh"

BUNDLE_DIR="${BUNDLE_DIR:-/tmp/e2e-diag-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$BUNDLE_DIR"
log "diag bundle → $BUNDLE_DIR"

kubectl get pods,asc,statefulset,configmap,pvc,pdb -A -o wide > "$BUNDLE_DIR/state.txt" 2>&1 || true
kubectl describe asc -A > "$BUNDLE_DIR/describe-asc.txt" 2>&1 || true
kubectl get events -A --sort-by='.lastTimestamp' > "$BUNDLE_DIR/events.txt" 2>&1 || true

op_pod=$(kubectl get pod -n "$NS_OPERATOR" -l control-plane=controller-manager -o name 2>/dev/null | head -1 || true)
[ -n "$op_pod" ] && kubectl logs -n "$NS_OPERATOR" "$op_pod" --tail=2000 > "$BUNDLE_DIR/operator.log" 2>&1 || true

api_pod=$(kubectl get pod -n "$NS_OPERATOR" -l app.kubernetes.io/component=ui-api -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)
if [ -n "$api_pod" ]; then
    kubectl logs -n "$NS_OPERATOR" "$api_pod" -c api --tail=2000 > "$BUNDLE_DIR/api.log" 2>&1 || true
    kubectl logs -n "$NS_OPERATOR" "$api_pod" -c api --tail=2000 --previous > "$BUNDLE_DIR/api-prev.log" 2>&1 || true
fi

for crd in aerospikeclusters.acko.io aerospikeclustertemplates.acko.io; do
    kubectl get crd "$crd" -o yaml >> "$BUNDLE_DIR/crd.yaml" 2>&1 || true
done
kubectl get validatingwebhookconfiguration -o yaml > "$BUNDLE_DIR/webhook.yaml" 2>&1 || true
kubectl get mutatingwebhookconfiguration -o yaml >> "$BUNDLE_DIR/webhook.yaml" 2>&1 || true

if helm status "$HELM_RELEASE" -n "$NS_OPERATOR" >/dev/null 2>&1; then
    helm get values "$HELM_RELEASE" -n "$NS_OPERATOR" > "$BUNDLE_DIR/helm-values.yaml" 2>&1 || true
    helm get manifest "$HELM_RELEASE" -n "$NS_OPERATOR" > "$BUNDLE_DIR/helm-manifest.yaml" 2>&1 || true
fi

if kubectl get ns "$NS_OTEL" >/dev/null 2>&1; then
    kubectl logs -n "$NS_OTEL" deploy/otel-collector --tail=200 > "$BUNDLE_DIR/collector.log" 2>&1 || true
fi

n=$(find "$BUNDLE_DIR" -type f | wc -l | tr -d ' ')
log "captured $n files"
echo "$BUNDLE_DIR"
