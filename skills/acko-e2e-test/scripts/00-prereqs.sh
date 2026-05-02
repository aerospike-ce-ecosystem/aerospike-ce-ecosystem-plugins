#!/usr/bin/env bash
# 00-prereqs.sh — verify host has the tools / runtime needed for e2e.
#
# Eval criteria (PASS when):
#   - kind / go / podman / kubectl / helm / yq / jq / curl all resolve
#   - go >= 1.25, kind >= 0.31
#   - podman machine is Running (macOS)
#   - the operator chart and Makefile are reachable from $OPERATOR_REPO
#
# Env: OPERATOR_REPO (default: workspace sibling)
# Exit: 0 on PASS, non-zero on FAIL. Last stdout line follows e2e:pass/fail contract.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="prereqs"

log_step "Checking required tools"
for t in kind go podman kubectl helm yq jq curl; do
    require_tool "$t"
    log_ok "$t found at $(command -v "$t")"
done

log_step "Checking versions"
go_ver=$(go version | awk '{print $3}' | sed 's/^go//')
kind_ver=$(kind --version | awk '{print $NF}')
log "go=$go_ver kind=$kind_ver"

# Numeric compare — bail if go < 1.25 or kind < 0.31.
ver_ge() {
    # ver_ge <a> <b>  → true if a >= b
    [ "$(printf '%s\n%s' "$1" "$2" | sort -V | head -1)" = "$2" ]
}
ver_ge "$go_ver" "1.25" || fail "$SCOPE" "go $go_ver < 1.25"
ver_ge "$kind_ver" "0.31" || fail "$SCOPE" "kind $kind_ver < 0.31"

log_step "Checking podman runtime"
if [ "$(uname)" = "Darwin" ]; then
    pm_state=$(podman machine list --format '{{.LastUp}}' 2>/dev/null | head -1)
    case "$pm_state" in
        "Currently running") log_ok "podman machine running" ;;
        *) fail "$SCOPE" "podman machine not running (state: ${pm_state:-unknown})" ;;
    esac
fi
podman info >/dev/null 2>&1 || fail "$SCOPE" "podman info failed (daemon/socket not reachable)"
log_ok "podman info OK"

log_step "Checking operator repo + chart"
[ -n "$OPERATOR_REPO" ] || fail "$SCOPE" "OPERATOR_REPO not resolvable"
[ -d "$OPERATOR_REPO" ] || fail "$SCOPE" "OPERATOR_REPO=$OPERATOR_REPO does not exist"
[ -f "$OPERATOR_REPO/Makefile" ] || fail "$SCOPE" "no Makefile in $OPERATOR_REPO"
require_chart
log_ok "operator repo at $OPERATOR_REPO"
log_ok "chart at $CHART_PATH"

pass "$SCOPE" "tools=$(go version | awk '{print $3}'),$(kind --version | awk '{print $3}') podman=running chart=ok"
