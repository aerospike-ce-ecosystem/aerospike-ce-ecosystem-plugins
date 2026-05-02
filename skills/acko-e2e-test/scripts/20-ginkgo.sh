#!/usr/bin/env bash
# 20-ginkgo.sh — run the in-tree Ginkgo e2e suite.
#
# Eval criteria (PASS when):
#   - `go test -tags=e2e ./test/e2e/` exits 0
#   - "Ran N of N Specs" with no FAIL lines
#
# We invoke `go test` directly instead of `make test-e2e` because the latter
# always runs `cleanup-test-e2e` at the end (deletes the Kind cluster), which
# would invalidate every step run after this one. The cluster is preserved
# unless the caller passes --tear-down.
#
# Modes (--mode):
#   smoke   → --label-filter='!heavy'   (~5–8 min)
#   full    → no filter                 (~15–60 min)  [default]
#   heavy   → --label-filter='heavy'    (~25–50 min)
#   focus:<regex>  → -ginkgo.focus='<regex>'  for iterating on one Context
#
# Flags:
#   --mode <mode>      see above
#   --timeout <dur>    go test -timeout (default: 60m)
#   --tear-down        run `make cleanup-test-e2e` after the run
#
# Env: OPERATOR_REPO, KIND_CLUSTER, CONTAINER_TOOL, KIND_PROVIDER

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="ginkgo"

mode="full"
timeout="60m"
teardown=0

while [ $# -gt 0 ]; do
    case "$1" in
        --mode)      mode="$2"; shift 2 ;;
        --timeout)   timeout="$2"; shift 2 ;;
        --tear-down) teardown=1; shift ;;
        *) fail "$SCOPE" "unknown flag: $1" ;;
    esac
done

ginkgo_args=()
case "$mode" in
    smoke) ginkgo_args+=(-ginkgo.label-filter='!heavy') ;;
    full)  ;;
    heavy) ginkgo_args+=(-ginkgo.label-filter='heavy') ;;
    focus:*) ginkgo_args+=(-ginkgo.focus="${mode#focus:}") ;;
    *) fail "$SCOPE" "unknown mode '$mode' (smoke|full|heavy|focus:<regex>)" ;;
esac

[ -d "$OPERATOR_REPO/test/e2e" ] || fail "$SCOPE" "no test/e2e under $OPERATOR_REPO"

log_step "Running Ginkgo suite mode=$mode timeout=$timeout"
log_file=/tmp/ginkgo-${mode//:/-}.log
(
    cd "$OPERATOR_REPO" && \
    KIND="$(command -v kind)" KIND_CLUSTER="$KIND_CLUSTER" \
    CONTAINER_TOOL="$CONTAINER_TOOL" KIND_PROVIDER="$KIND_PROVIDER" \
    KIND_EXPERIMENTAL_PROVIDER="$KIND_PROVIDER" \
    go test -tags=e2e -timeout "$timeout" ./test/e2e/ -v -ginkgo.v "${ginkgo_args[@]}"
) 2>&1 | tee "$log_file" >&2
exit_code=${PIPESTATUS[0]}

# Post-run summary
ran_line=$(grep -E '^Ran [0-9]+ of [0-9]+ Specs' "$log_file" | tail -1 || true)
n_fail=$(grep -c '^FAIL!' "$log_file" || true)

if [ "$exit_code" -ne 0 ] || [ "${n_fail:-0}" -gt 0 ]; then
    [ "$teardown" -eq 1 ] && (cd "$OPERATOR_REPO" && make cleanup-test-e2e >&2 || true)
    fail "$SCOPE" "go test exit=$exit_code FAIL!=$n_fail (log: $log_file)"
fi

[ "$teardown" -eq 1 ] && (cd "$OPERATOR_REPO" && make cleanup-test-e2e >&2 || true)
pass "$SCOPE" "${ran_line:-passed} mode=$mode (log: $log_file)"
