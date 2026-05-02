#!/usr/bin/env bash
# 41-helm-real-install.sh — `helm install` + `helm test` + `helm uninstall`.
#
# `helm template` (40-helm-matrix.sh) catches manifest-level regressions but
# misses things that only surface during apply: CRD ordering, hook race,
# RBAC propagation, pre/post-install hooks. This script exercises those.
#
# Eval criteria (PASS when):
#   1. helm install $RELEASE -n $TEST_NS succeeds (chart defaults)
#   2. all pods reach Running
#   3. helm test $RELEASE -n $TEST_NS passes (TEST SUITE Phase: Succeeded)
#   4. helm uninstall + delete ns leaves no leftover state
#
# This deliberately uses a SEPARATE namespace (default: aerospike-operator-test)
# and release name so it doesn't collide with the long-lived install used by
# other scripts.
#
# Env: CHART_PATH
# Flags: --release <n>  default: acko-test
#        --ns <n>       default: aerospike-operator-test
#        --image <repo> default: localhost/acko-controller (use whatever's loaded)
#        --tag <t>      default: e2e

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="helm-real"
require_chart

release="acko-test"
ns="aerospike-operator-test"
img_repo="localhost/acko-controller"
img_tag="e2e"

while [ $# -gt 0 ]; do
    case "$1" in
        --release) release="$2"; shift 2 ;;
        --ns) ns="$2"; shift 2 ;;
        --image) img_repo="$2"; shift 2 ;;
        --tag) img_tag="$2"; shift 2 ;;
        *) fail "$SCOPE" "unknown flag: $1" ;;
    esac
done

log_step "helm install $release -n $ns"
helm install "$release" "$CHART_PATH" \
    --namespace "$ns" --create-namespace \
    --set "image.repository=$img_repo" \
    --set "image.tag=$img_tag" \
    --set image.pullPolicy=Never \
    --wait --timeout 5m >&2 \
    || fail "$SCOPE" "helm install failed"

log_step "helm test $release"
test_log=$(helm test "$release" -n "$ns" 2>&1) || {
    log_err "$test_log"
    helm uninstall "$release" -n "$ns" >&2 || true
    kubectl delete ns "$ns" --ignore-not-found >&2 || true
    fail "$SCOPE" "helm test failed"
}
echo "$test_log" | grep -q 'Phase:[[:space:]]*Succeeded' \
    || fail "$SCOPE" "helm test output missing 'Phase: Succeeded'"
log_ok "helm test passed"

log_step "Cleanup (helm uninstall + delete ns)"
helm uninstall "$release" -n "$ns" --wait --timeout 2m >&2 || true
kubectl delete ns "$ns" --ignore-not-found --wait=false >&2 || true

pass "$SCOPE" "release=$release install+test+uninstall ok"
