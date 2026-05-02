#!/usr/bin/env bash
# load-image.sh — generic podman save → kind load image-archive.
# Used for the OTel collector image and patched ui-api image during dev.
#
# Usage: ./load-image.sh <image[:tag]>

source "$(dirname "$0")/_common.sh"

img="${1:?usage: $0 <image[:tag]>}"

log "pulling $img (if not local)"
"$CONTAINER_TOOL" pull "$img" >&2 || true

log "saving $img → /tmp/load-image.tar"
"$CONTAINER_TOOL" save -o /tmp/load-image.tar "$img" >&2

log "loading into Kind '$KIND_CLUSTER'"
KIND_EXPERIMENTAL_PROVIDER="$KIND_PROVIDER" \
    kind load image-archive /tmp/load-image.tar --name "$KIND_CLUSTER" >&2

rm -f /tmp/load-image.tar
log "loaded"
