#!/usr/bin/env bash
# kind-up.sh — bring up the Kind cluster + build/load the operator image.
#
# Idempotent: reuses an existing cluster, re-builds & re-loads the image
# every run so a code change in the operator picks up.
#
# Env: KIND_CLUSTER, CONTAINER_TOOL, KIND_PROVIDER, OPERATOR_REPO, IMG

source "$(dirname "$0")/_common.sh"
[ -d "$OPERATOR_REPO" ] || die "OPERATOR_REPO=$OPERATOR_REPO not found"

if kind get clusters 2>/dev/null | grep -qx "$KIND_CLUSTER"; then
    log "Kind cluster '$KIND_CLUSTER' already exists — reusing"
else
    log "Creating Kind cluster '$KIND_CLUSTER' (~60–90s)"
    (cd "$OPERATOR_REPO" && make setup-test-e2e) >&2
fi

kubectl config use-context "kind-$KIND_CLUSTER" >&2
kubectl wait --for=condition=Ready nodes --all --timeout=3m >&2

log "Building operator image $IMG"
(cd "$OPERATOR_REPO" && make docker-build IMG="$IMG" CONTAINER_TOOL="$CONTAINER_TOOL") >&2

log "Loading $IMG into Kind"
tar=/tmp/kind-image-load.tar
"$CONTAINER_TOOL" save -o "$tar" "$IMG" >&2
KIND_EXPERIMENTAL_PROVIDER="$KIND_PROVIDER" \
    kind load image-archive "$tar" --name "$KIND_CLUSTER" >&2
rm -f "$tar"

log "Verifying image present on every node"
img_base=$(echo "$IMG" | cut -d: -f1 | sed 's|.*/||')
for n in $(kubectl get nodes -o name | sed 's|node/||'); do
    "$CONTAINER_TOOL" exec "$n" crictl images 2>/dev/null \
        | grep -q "$img_base" \
        || die "image $IMG missing on node $n"
done

log "Kind cluster + image ready"
