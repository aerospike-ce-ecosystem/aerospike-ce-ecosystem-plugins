#!/usr/bin/env bash
# run-all.sh — orchestrate a full ACKO e2e run.
#
# Each step is one of the numbered scripts. We tally e2e:pass / e2e:fail lines
# and print the standard SKILL.md Section 8 report at the end.
#
# Modes:
#   smoke      40 → 41 → 10 → 11 → 12 → 21 → 30 → 33 → 31 → 32 → 99 (no Ginkgo)
#   full       40 → 41 → 10 → 11 → 12 → 21 → 30 → 33 → 31 → 32 → 20[full] → 99
#   chart      40 → 41 (no cluster work; fast PR gate)
#   ginkgo     10 → 20[<mode>] → 99[--kind]
#
# Flags:
#   --mode <m>           default: full
#   --ginkgo-mode <m>    forwarded to 20-ginkgo.sh (smoke|full|heavy|focus:<re>)
#   --tear-down-kind     also delete the Kind cluster at the end
#   --skip-prereqs       skip 00-prereqs.sh (you already validated)
#   --bundle-on-fail     capture diag bundle when any step fails (default: on)
#
# Exit: 0 if every executed step PASSed, 1 otherwise.

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="run-all"

mode="full"
ginkgo_mode="full"
tear_down=0
skip_prereqs=0
bundle=1

while [ $# -gt 0 ]; do
    case "$1" in
        --mode) mode="$2"; shift 2 ;;
        --ginkgo-mode) ginkgo_mode="$2"; shift 2 ;;
        --tear-down-kind) tear_down=1; shift ;;
        --skip-prereqs) skip_prereqs=1; shift ;;
        --bundle-on-fail) bundle=1; shift ;;
        --no-bundle) bundle=0; shift ;;
        *) fail "$SCOPE" "unknown flag: $1" ;;
    esac
done

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
declare -a results=()      # "pass:scope:summary" or "fail:scope:reason"
declare -a failed_steps=()
overall_start=$(date +%s)

run_step() {
    # run_step <script_name> [args...]
    local script="$1"; shift
    local path="$scripts_dir/$script"
    [ -x "$path" ] || chmod +x "$path"

    local label="${script%.sh}"
    log_step ">>> $label $* <<<"
    local out_file="/tmp/run-all-${label}.out"
    local rc=0
    "$path" "$@" 2>&1 | tee "$out_file" >&2 || rc=$?
    # Parse the contract line (last e2e:pass or e2e:fail)
    local contract
    contract=$(grep -E '^e2e:(pass|fail)\[' "$out_file" | tail -1 || true)
    if [[ "$contract" == e2e:pass* ]]; then
        local scope summary
        scope=$(echo "$contract" | sed -E 's/^e2e:pass\[scope=([^]]+)\].*$/\1/')
        summary=$(echo "$contract" | sed -E 's/^e2e:pass\[scope=[^]]+\] *//')
        results+=("pass:$scope:$summary")
        log_ok "$label PASS — $summary"
        return 0
    elif [[ "$contract" == e2e:fail* ]]; then
        local scope reason
        scope=$(echo "$contract" | sed -E 's/^e2e:fail\[scope=([^]]+)\].*$/\1/')
        reason=$(echo "$contract" | sed -E 's/^e2e:fail\[scope=[^]]+\] reason: *//')
        results+=("fail:$scope:$reason")
        failed_steps+=("$label")
        log_err "$label FAIL — $reason"
        return 1
    else
        results+=("fail:$label:no contract line in output")
        failed_steps+=("$label")
        log_err "$label produced no contract line (rc=$rc)"
        return 1
    fi
}

declare -a sequence=()
case "$mode" in
    smoke)
        sequence=(40-helm-matrix.sh 41-helm-real-install.sh 10-kind-up.sh 11-cert-manager.sh \
                  12-helm-install.sh 21-asc-create-smoke.sh:--keep 30-api-crud-smoke.sh \
                  33-api-k8s-create-smoke.sh 31-logging.sh 32-otel-runtime.sh 99-cleanup.sh)
        ;;
    full)
        sequence=(40-helm-matrix.sh 41-helm-real-install.sh 10-kind-up.sh 11-cert-manager.sh \
                  12-helm-install.sh 21-asc-create-smoke.sh:--keep 30-api-crud-smoke.sh \
                  33-api-k8s-create-smoke.sh 31-logging.sh 32-otel-runtime.sh \
                  99-cleanup.sh 20-ginkgo.sh:--mode:full)
        ;;
    chart)
        sequence=(40-helm-matrix.sh)
        ;;
    ginkgo)
        sequence=(10-kind-up.sh "20-ginkgo.sh:--mode:$ginkgo_mode")
        ;;
    *)
        fail "$SCOPE" "unknown --mode '$mode' (smoke|full|chart|ginkgo)"
        ;;
esac

[ "$skip_prereqs" -eq 0 ] && run_step 00-prereqs.sh

trap 'true' ERR
last_rc=0
for entry in "${sequence[@]}"; do
    # Allow inline args separated by ':'
    IFS=':' read -ra parts <<<"$entry"
    script="${parts[0]}"
    args=("${parts[@]:1}")
    # bash 3.2 + set -u: ${args[@]} on empty array is "unbound"; use the
    # ${arr[@]+"${arr[@]}"} idiom to expand safely.
    if ! run_step "$script" ${args[@]+"${args[@]}"}; then
        last_rc=1
        # Don't abort on chart failures or cleanup failures, but DO abort if a
        # setup step (10/11/12) fails — later steps would just cascade.
        case "$script" in
            10-kind-up.sh|11-cert-manager.sh|12-helm-install.sh)
                log_err "setup step failed — aborting remaining sequence"
                break
                ;;
        esac
    fi
done

# Collect diagnostics if anything failed
if [ "$last_rc" -ne 0 ] && [ "$bundle" -eq 1 ]; then
    log_step "Collecting diagnostic bundle"
    "$scripts_dir/60-diag-bundle.sh" >&2 || true
fi

# Optional: kind teardown
if [ "$tear_down" -eq 1 ]; then
    "$scripts_dir/99-cleanup.sh" --kind >&2 || true
fi

# ---- Final report (Section 8 format) ----
overall_dur=$(( $(date +%s) - overall_start ))
n_pass=$(printf '%s\n' "${results[@]}" | grep -c '^pass:' || true)
n_fail=$(printf '%s\n' "${results[@]}" | grep -c '^fail:' || true)
total=${#results[@]}

branch=$(git -C "$OPERATOR_REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)
sha=$(git -C "$OPERATOR_REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)
date_iso=$(date -u +%Y-%m-%dT%H:%MZ)

printf '\n========================================================================\n'
printf 'e2e run on %s@%s — %s\n' "$branch" "$sha" "$date_iso"
printf 'Mode:        %s\n' "$mode"
printf 'Duration:    %sm %ss\n' "$((overall_dur / 60))" "$((overall_dur % 60))"
printf 'Outcome:     %s\n\n' "$([ "$last_rc" -eq 0 ] && echo PASS || echo FAIL)"

printf 'Steps: %d passed, %d failed (of %d total)\n\n' "$n_pass" "$n_fail" "$total"
for r in "${results[@]}"; do
    case "$r" in
        pass:*) printf '  ✅ %-22s %s\n' "$(echo "$r" | cut -d: -f2)" "$(echo "$r" | cut -d: -f3-)" ;;
        fail:*) printf '  ❌ %-22s %s\n' "$(echo "$r" | cut -d: -f2)" "$(echo "$r" | cut -d: -f3-)" ;;
    esac
done

if [ "${#failed_steps[@]}" -gt 0 ]; then
    printf '\nFailed steps: %s\n' "${failed_steps[*]}"
    printf 'Per-step output:  /tmp/run-all-<step>.out\n'
    printf 'Diagnostic bundle: ls /tmp/e2e-diag-* 2>/dev/null | tail -1\n'
fi

printf '========================================================================\n'

exit "$last_rc"
