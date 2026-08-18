#!/usr/bin/env bash
# Clone every repo in sources.lock at its pinned SHA.
#
# Usage: scripts/fetch_sources.sh [dest-dir]     (default: .source-cache)
#
# Re-running is cheap: a checkout already at the pinned SHA is left alone, so
# this doubles as the local dev loop. Fetches are blobless and single-branch —
# the checker only reads a handful of files, and full history costs minutes in
# CI for nothing.
set -euo pipefail

DEST="${1:-.source-cache}"
LOCK="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sources.lock"

[ -f "$LOCK" ] || { echo "error: no sources.lock at $LOCK" >&2; exit 2; }
mkdir -p "$DEST"

while read -r name url sha; do
    case "$name" in ''|\#*) continue ;; esac
    [ -n "${sha:-}" ] || { echo "error: no SHA for $name in sources.lock" >&2; exit 2; }
    target="$DEST/$name"

    if [ -d "$target/.git" ] && [ "$(git -C "$target" rev-parse HEAD 2>/dev/null)" = "$sha" ]; then
        echo "  $name already at ${sha:0:12}"
        continue
    fi

    echo "  fetching $name @ ${sha:0:12}"
    if [ ! -d "$target/.git" ]; then
        git init -q "$target"
        git -C "$target" remote add origin "$url"
    fi
    # A pinned SHA may not be a branch tip, so fetch the object directly.
    git -C "$target" fetch -q --depth 1 --filter=blob:none origin "$sha"
    git -C "$target" checkout -q --detach FETCH_HEAD
done < "$LOCK"

echo "sources ready in $DEST"
