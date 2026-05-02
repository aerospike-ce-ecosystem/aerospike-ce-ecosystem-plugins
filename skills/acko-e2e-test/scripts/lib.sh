# shellcheck shell=bash
# Shared helpers for ACKO e2e scripts. Source from every script:
#   source "$(dirname "$0")/lib.sh"
#
# Output contract every script honors:
#   * On success, the LAST line on stdout MUST be:   e2e:pass[scope=<name>] <one-line summary>
#   * On failure, the LAST line on stdout MUST be:   e2e:fail[scope=<name>] reason: <one-liner>
#   Exit code matches (0 / non-zero).
#
# The orchestrator (run-all.sh) parses these lines to assemble the final report.
# Diagnostics, kubectl output, etc. go to STDERR so they don't pollute the contract.

set -euo pipefail

# --------------------------------------------------------------------------
# Defaults — override via env. We intentionally match the values that ACKO's
# Makefile and BeforeSuite hardcode so scripts compose without surprises.
# --------------------------------------------------------------------------
: "${KIND_CLUSTER:=aerospike-ce-kubernetes-operator-test-e2e}"
: "${CONTAINER_TOOL:=podman}"
: "${KIND_PROVIDER:=podman}"
: "${KIND_EXPERIMENTAL_PROVIDER:=$KIND_PROVIDER}"
: "${NS_OPERATOR:=aerospike-operator}"
: "${NS_AEROSPIKE:=aerospike}"
: "${NS_OTEL:=otel}"
: "${HELM_RELEASE:=acko}"
# IMG matches test/e2e/e2e_suite_test.go:47 — BeforeSuite hardcodes this tag.
# Pre-loading any other tag is wasted work because Ginkgo will re-build with
# this name anyway.
: "${IMG:=ghcr.io/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator:v0.0.1}"
: "${API_IMG:=ghcr.io/aerospike-ce-ecosystem/aerospike-cluster-manager-api:latest}"
: "${OPERATOR_REPO:=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../aerospike-ce-kubernetes-operator" 2>/dev/null && pwd || echo "")}"
: "${CHART_PATH:=${OPERATOR_REPO}/charts/aerospike-ce-kubernetes-operator}"
: "${CERT_MANAGER_VERSION:=v1.19.3}"
: "${COLLECTOR_IMAGE:=docker.io/otel/opentelemetry-collector-contrib:latest}"

export KIND_CLUSTER CONTAINER_TOOL KIND_PROVIDER KIND_EXPERIMENTAL_PROVIDER

# --------------------------------------------------------------------------
# Logging — colored to stderr, contract lines to stdout.
# --------------------------------------------------------------------------
if [ -t 2 ]; then
    _C_RESET=$'\033[0m'; _C_INFO=$'\033[36m'; _C_WARN=$'\033[33m'
    _C_ERR=$'\033[31m'; _C_OK=$'\033[32m'; _C_BOLD=$'\033[1m'
else
    _C_RESET=''; _C_INFO=''; _C_WARN=''; _C_ERR=''; _C_OK=''; _C_BOLD=''
fi

log()       { printf '%s[%s]%s %s\n' "$_C_INFO"  "$(date +%H:%M:%S)" "$_C_RESET" "$*" >&2; }
log_warn()  { printf '%s[%s WARN]%s %s\n' "$_C_WARN" "$(date +%H:%M:%S)" "$_C_RESET" "$*" >&2; }
log_err()   { printf '%s[%s ERR]%s %s\n'  "$_C_ERR"  "$(date +%H:%M:%S)" "$_C_RESET" "$*" >&2; }
log_step()  { printf '%s[%s]%s %s%s%s\n' "$_C_INFO" "$(date +%H:%M:%S)" "$_C_RESET" "$_C_BOLD" "$*" "$_C_RESET" >&2; }
log_ok()    { printf '%s[%s OK]%s %s\n'  "$_C_OK"   "$(date +%H:%M:%S)" "$_C_RESET" "$*" >&2; }

# Final contract emitter. Use these — never raw printf for the contract line.
pass() {
    local scope="$1"; shift
    printf 'e2e:pass[scope=%s] %s\n' "$scope" "$*"
    exit 0
}
fail() {
    local scope="$1"; shift
    printf 'e2e:fail[scope=%s] reason: %s\n' "$scope" "$*"
    exit 1
}

# --------------------------------------------------------------------------
# Asserts — print a clean error context and call fail(scope, ...).
# Each assert needs the caller to have set $SCOPE so failures route properly.
# --------------------------------------------------------------------------
: "${SCOPE:=unknown}"

assert_eq() {
    # assert_eq <expected> <actual> <description>
    local expected="$1" actual="$2" desc="$3"
    if [ "$expected" != "$actual" ]; then
        log_err "$desc — expected '$expected', got '$actual'"
        fail "$SCOPE" "$desc (expected='$expected', got='$actual')"
    fi
    log_ok "$desc (= '$expected')"
}

assert_match() {
    # assert_match <regex> <text> <description>
    local re="$1" text="$2" desc="$3"
    if ! grep -qE "$re" <<<"$text"; then
        log_err "$desc — pattern '$re' not in text"
        log_err "  text: $(echo "$text" | head -3)"
        fail "$SCOPE" "$desc (pattern='$re' not matched)"
    fi
    log_ok "$desc (matches '$re')"
}

assert_count() {
    # assert_count <op> <expected> <actual> <description>
    # op: eq, ge, le, gt, lt
    local op="$1" expected="$2" actual="$3" desc="$4" ok=0
    case "$op" in
        eq) [ "$actual" -eq "$expected" ] && ok=1 ;;
        ge) [ "$actual" -ge "$expected" ] && ok=1 ;;
        le) [ "$actual" -le "$expected" ] && ok=1 ;;
        gt) [ "$actual" -gt "$expected" ] && ok=1 ;;
        lt) [ "$actual" -lt "$expected" ] && ok=1 ;;
        *) fail "$SCOPE" "assert_count: unknown op '$op'" ;;
    esac
    if [ "$ok" -ne 1 ]; then
        log_err "$desc — expected $op $expected, got $actual"
        fail "$SCOPE" "$desc (op=$op expected=$expected actual=$actual)"
    fi
    log_ok "$desc ($actual $op $expected)"
}

assert_http() {
    # assert_http <expected_status> <method> <url> [curl_extra_args...]
    local expected="$1" method="$2" url="$3"; shift 3
    local actual
    actual=$(curl -sS -o /dev/null -w '%{http_code}' -X "$method" "$@" "$url" || echo "000")
    if [ "$actual" != "$expected" ]; then
        log_err "$method $url — expected HTTP $expected, got $actual"
        fail "$SCOPE" "$method $url got $actual (want $expected)"
    fi
    log_ok "$method $url → $actual"
}

# --------------------------------------------------------------------------
# Polling helpers
# --------------------------------------------------------------------------
wait_for() {
    # wait_for <timeout_sec> <interval_sec> <description> -- <command...>
    local timeout="$1" interval="$2" desc="$3"; shift 3
    [ "$1" = "--" ] && shift
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if "$@" >/dev/null 2>&1; then
            log_ok "$desc (within $timeout s)"
            return 0
        fi
        sleep "$interval"
    done
    log_err "$desc — timeout after $timeout s"
    fail "$SCOPE" "$desc (timeout after ${timeout}s)"
}

wait_phase_completed() {
    # wait_phase_completed <ns> <asc-name> <timeout_sec>
    local ns="$1" name="$2" timeout="${3:-180}"
    local deadline=$(( $(date +%s) + timeout ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        local phase
        phase=$(kubectl get asc -n "$ns" "$name" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
        if [ "$phase" = "Completed" ]; then
            log_ok "asc/$name in ns/$ns reached Completed"
            return 0
        fi
        log "asc/$name phase=$phase, waiting…"
        sleep 5
    done
    fail "$SCOPE" "asc/$name did not reach Completed within ${timeout}s"
}

# --------------------------------------------------------------------------
# Tooling guards
# --------------------------------------------------------------------------
require_tool() {
    local t="$1"
    command -v "$t" >/dev/null 2>&1 || fail "${SCOPE:-prereqs}" "missing tool: $t"
}

require_chart() {
    [ -d "$CHART_PATH" ] || fail "${SCOPE:-prereqs}" "chart not found at $CHART_PATH (override CHART_PATH)"
}

# --------------------------------------------------------------------------
# Port-forward management — every script that opens a PF must register the
# PID via pf_register so pf_cleanup_all kills it on exit.
# --------------------------------------------------------------------------
# bash 3.2 (macOS default) doesn't support `declare -g`, but top-level array
# assignment is already global, so the bare form is fine.
_PF_PIDS=()

pf_open() {
    # pf_open <ns> <svc> <local_port> <svc_port> — returns the PID on stdout
    local ns="$1" svc="$2" local_port="$3" svc_port="$4"
    local logfile="/tmp/pf-${svc}-${local_port}.log"
    : > "$logfile"
    kubectl port-forward -n "$ns" "svc/$svc" "${local_port}:${svc_port}" >"$logfile" 2>&1 &
    local pid=$!
    _PF_PIDS+=("$pid")
    # Wait briefly for the forward to be ready
    local deadline=$(( $(date +%s) + 10 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if grep -q "Forwarding from" "$logfile" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        sleep 0.3
    done
    fail "$SCOPE" "port-forward to svc/$svc:$svc_port did not become ready"
}

pf_cleanup_all() {
    local pid
    for pid in "${_PF_PIDS[@]:-}"; do
        [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
    done
    _PF_PIDS=()
}

trap 'pf_cleanup_all' EXIT

# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------
ns_exists() { kubectl get ns "$1" >/dev/null 2>&1; }

# Returns 0 if a deploy is Available with all replicas Ready.
deploy_ready() {
    local ns="$1" name="$2"
    kubectl wait --for=condition=Available "deploy/$name" -n "$ns" --timeout=1s >/dev/null 2>&1
}

# Stable hostname helper — Aerospike service inside a cluster.
asc_seed_host() {
    # asc_seed_host <asc-name> <ns>
    printf '%s.%s.svc.cluster.local' "$1" "$2"
}
