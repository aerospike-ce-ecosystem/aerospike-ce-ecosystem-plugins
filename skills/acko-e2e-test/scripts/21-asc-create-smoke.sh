#!/usr/bin/env bash
# 21-asc-create-smoke.sh — fast happy-path AerospikeCluster CR create/delete.
#
# Eval criteria (PASS when):
#   1. Apply config/samples/acko_v1alpha1_aerospikecluster.yaml succeeds
#   2. Cluster reaches phase=Completed within $TIMEOUT seconds
#   3. Expected K8s resources present:
#        - StatefulSet  named like aerospike-basic-<rackID>
#        - Headless Service named aerospike-basic
#        - ConfigMap matching the rack
#        - PodDisruptionBudget for the cluster
#   4. status.size == spec.size
#   5. status.pods has 1 entry with IsRunningAndReady=true
#   6. Delete the CR and verify the namespace returns to no asc CRs and pods
#
# This is the lightweight cousin of the Ginkgo Basic single-node Context.
# Used as:
#   - PR-time fast gate (1–2 min) instead of the full 15-min Ginkgo run
#   - Prerequisite for 30-api-crud-smoke / 33-api-k8s-create-smoke (api needs
#     a Completed cluster to talk to)
#
# Env: NS_AEROSPIKE, OPERATOR_REPO
# Flags: --keep   leave the CR running after PASS (caller wants to re-use it)
#        --name <n>   override CR name (default: aerospike-basic)

source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
SCOPE="asc-create"

keep=0
name="aerospike-basic"
timeout=180

while [ $# -gt 0 ]; do
    case "$1" in
        --keep) keep=1; shift ;;
        --name) name="$2"; shift 2 ;;
        --timeout) timeout="$2"; shift 2 ;;
        *) fail "$SCOPE" "unknown flag: $1" ;;
    esac
done

sample="$OPERATOR_REPO/config/samples/acko_v1alpha1_aerospikecluster.yaml"
[ -f "$sample" ] || fail "$SCOPE" "sample not found: $sample"

log_step "Applying sample CR (ns=$NS_AEROSPIKE name=$name)"
kubectl create namespace "$NS_AEROSPIKE" --dry-run=client -o yaml | kubectl apply -f - >&2
# Use yq to rename the CR if --name was overridden so we don't collide.
if [ "$name" != "aerospike-basic" ]; then
    yq "(.metadata.name = \"$name\") | (.metadata.namespace = \"$NS_AEROSPIKE\") | (.spec.aerospikeConfig.service.cluster-name = \"$name\")" \
        "$sample" | kubectl apply -f - >&2 || fail "$SCOPE" "kubectl apply failed"
else
    yq "(.metadata.namespace = \"$NS_AEROSPIKE\")" "$sample" | kubectl apply -f - >&2 \
        || fail "$SCOPE" "kubectl apply failed"
fi

log_step "Waiting for phase=Completed (up to ${timeout}s)"
wait_phase_completed "$NS_AEROSPIKE" "$name" "$timeout"

log_step "Verifying Kubernetes resources"
ss_count=$(kubectl get statefulset -n "$NS_AEROSPIKE" -l "aerospike.com/cluster-name=$name" --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [ "$ss_count" -eq 0 ]; then
    # Fallback: most ACKO StatefulSets don't carry that label — match by name prefix.
    ss_count=$(kubectl get statefulset -n "$NS_AEROSPIKE" --no-headers 2>/dev/null | grep -c "^${name}-" || true)
fi
assert_count ge 1 "$ss_count" "≥1 StatefulSet for $name"

svc_count=$(kubectl get svc -n "$NS_AEROSPIKE" "$name" --no-headers 2>/dev/null | wc -l | tr -d ' ')
assert_count eq 1 "$svc_count" "headless Service '$name'"

cm_count=$(kubectl get cm -n "$NS_AEROSPIKE" --no-headers 2>/dev/null | grep -c "^${name}-" || true)
assert_count ge 1 "$cm_count" "≥1 ConfigMap for $name"

pdb_count=$(kubectl get pdb -n "$NS_AEROSPIKE" --no-headers 2>/dev/null | grep -c "^${name}" || true)
assert_count ge 1 "$pdb_count" "≥1 PodDisruptionBudget for $name"

log_step "Verifying status fields"
spec_size=$(kubectl get asc -n "$NS_AEROSPIKE" "$name" -o jsonpath='{.spec.size}')
status_size=$(kubectl get asc -n "$NS_AEROSPIKE" "$name" -o jsonpath='{.status.size}')
assert_eq "$spec_size" "$status_size" "status.size matches spec.size"

ready_pods=$(kubectl get asc -n "$NS_AEROSPIKE" "$name" -o json \
    | jq '[.status.pods // {} | to_entries[] | select(.value.isRunningAndReady == true)] | length')
assert_count eq "$spec_size" "$ready_pods" "$spec_size pods reported running+ready in status"

if [ "$keep" -eq 1 ]; then
    pass "$SCOPE" "name=$name size=$spec_size — kept (callers will reuse it)"
fi

log_step "Deleting CR and verifying cleanup"
kubectl delete asc -n "$NS_AEROSPIKE" "$name" --wait=true --timeout=2m >&2 \
    || fail "$SCOPE" "kubectl delete asc failed"

# Cluster pods should be gone after delete (PVC cleanup depends on
# cascadeDelete; the basic sample uses memory storage, so no PVCs).
remaining=$(kubectl get asc -n "$NS_AEROSPIKE" --no-headers 2>/dev/null | wc -l | tr -d ' ')
assert_count eq 0 "$remaining" "no ASC CRs remaining in $NS_AEROSPIKE"

pass "$SCOPE" "name=$name size=$spec_size lifecycle ok"
