#!/usr/bin/env bash
# 10-kind-up.sh — bring up the Kind cluster + load the operator image.
#
# Eval criteria (PASS when):
#   - Kind cluster $KIND_CLUSTER exists with all 4 default nodes Ready
#   - $IMG is loaded on every node (control-plane + 3 workers)
#
# Why $IMG defaults to ghcr.io/.../v0.0.1: BeforeSuite in
# test/e2e/e2e_suite_test.go:47 hardcodes that tag. Loading any other tag
# is wasted work — Ginkgo will rebuild and re-load with v0.0.1 anyway.
# (We still build under that tag here so the helm-install layer can run
# before the Ginkgo layer.)
#
# Env: KIND_CLUSTER, CONTAINER_TOOL=podman, KIND_PROVIDER=podman, IMG, OPERATOR_REPO
# Exit: 0 PASS / 1 FAIL

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="kind-up"

[ -d "$OPERATOR_REPO" ] || fail "$SCOPE" "OPERATOR_REPO=$OPERATOR_REPO not found"

log_step "Ensuring Kind cluster '$KIND_CLUSTER' exists"
if kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"; then
    log_ok "Kind cluster already exists — reusing"
else
    log "Creating cluster (this takes ~60–90s)"
    (cd "$OPERATOR_REPO" && make setup-test-e2e) >&2 || fail "$SCOPE" "make setup-test-e2e failed"
fi

kubectl config use-context "kind-$KIND_CLUSTER" >&2 || fail "$SCOPE" "cannot switch context"

log_step "Waiting for nodes Ready"
kubectl wait --for=condition=Ready nodes --all --timeout=3m >&2 || fail "$SCOPE" "nodes did not become Ready"
n_nodes=$(kubectl get nodes --no-headers | wc -l | tr -d ' ')
assert_count ge 4 "$n_nodes" "expected ≥4 Kind nodes"

log_step "Building operator image $IMG via $CONTAINER_TOOL"
(cd "$OPERATOR_REPO" && make docker-build IMG="$IMG" CONTAINER_TOOL="$CONTAINER_TOOL") >&2 \
    || fail "$SCOPE" "docker-build failed for $IMG"

log_step "Loading image into Kind via tarball"
local_tag="${IMG#localhost/}"   # podman saves with the registry prefix; keep IMG as-is
tar=/tmp/acko-image-load.tar
"$CONTAINER_TOOL" save -o "$tar" "$IMG" >&2 || fail "$SCOPE" "$CONTAINER_TOOL save failed"
KIND_EXPERIMENTAL_PROVIDER="$KIND_PROVIDER" \
    kind load image-archive "$tar" --name "$KIND_CLUSTER" >&2 \
    || fail "$SCOPE" "kind load image-archive failed"
rm -f "$tar"

log_step "Verifying image on every node"
missing=0
for n in $(kubectl get nodes -o name | sed 's|node/||'); do
    if podman exec "$n" crictl images 2>/dev/null | grep -q "$(echo "$IMG" | cut -d: -f1 | sed 's|.*/||')"; then
        log_ok "$n has the image"
    else
        log_err "$n is missing the image"
        missing=$((missing + 1))
    fi
done
[ "$missing" -eq 0 ] || fail "$SCOPE" "$missing nodes missing $IMG"

pass "$SCOPE" "cluster=$KIND_CLUSTER nodes=$n_nodes image=$IMG"
