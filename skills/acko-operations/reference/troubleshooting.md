# Troubleshooting Guide

Symptom-based diagnostic reference for ACKO Aerospike clusters.

---

## Symptom-Based Diagnosis

| Symptom | Diagnostic Command | Likely Cause | Resolution |
|---------|-------------------|--------------|------------|
| Phase = `Error` | `kubectl get asc <name> -o jsonpath='{.status.lastReconcileError}'` | Invalid config, image pull failure, resource exhaustion | Read the error message, fix the root cause, re-apply the CR |
| Phase = `ConfigDegraded` | `kubectl get asc <name> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' \| jq` | 2PC dynamic config rollback failed; pods inconsistent | Do NOT toggle `enableDynamicConfigUpdate`; let the operator cold-restart on next reconcile. If the loop continues, revert spec to known-good values |
| Phase = `WaitingForMigration` | `kubectl exec <pod> -c aerospike-server -- asinfo -v 'statistics' \| tr ';' '\n' \| grep migrate` | Data migration in progress (normal during scale-down) | Wait for completion (operator auto-proceeds) |
| `InProgress` stuck > 5 min | `kubectl get pvc -n <ns> -l aerospike.io/cr-name=<name>` | PVC Pending, ImagePull failure, scheduling failure | Check StorageClass, image name, resource availability |
| `phase=BackoffActive`, `ReconcileHealthy=True` (transient) | `kubectl get asc <name> -o jsonpath='{.status.conditions[?(@.type=="ReconcileHealthy")]}'` | Reconcile circuit breaker tripped on a transient cause | Fix transient cause; operator auto-retries with backoff |
| `phase=BackoffActive`, `ReconcileHealthy=False, reason=PermanentError` | Same jsonpath returns `status=False, reason=PermanentError` | Validation/configgen/secret error; no auto-retry | Fix root cause; toggle `paused: true → null` to clear stale `failedReconcileCount`/`lastReconcileError` (or edit spec to retrigger) |
| `phase=ACLSync` (stuck) | `kubectl get asc <name> -o jsonpath='{.status.conditions[?(@.type=="ACLSynced")]}'` | ACL sync failing — cluster does NOT reach Completed | Fix the password Secret / role scopes; reconcile requeues ~30s |
| Operations stuck `InProgress`, webhook rejects new edit | `kubectl get asc <name> -o jsonpath='{.status.operation.phase}'` | Cannot modify `spec.operations[]` while one is `InProgress` | Wait for the in-flight operation to complete or fail; only then queue the next |
| Pod `CrashLoopBackOff` | `kubectl logs <pod> -c aerospike-server --previous` | Config parse error, OOM, invalid parameters | Check server logs, fix aerospikeConfig |
| Webhook rejects CR (shape) | Read `kubectl apply` error output | Wrong YAML shape | `service`/`network` maps; `logging` a list; namespace entries maps with unique `name` |
| Webhook rejects CR (CE constraint) | Read `kubectl apply` error output | size>8, namespaces>2, dup namespace, enterprise/`ce-<8` image, xdr/tls, enterprise logging context, scoped admin privilege, per-rack CE violation | Fix per `validation-rules.md` |
| `dynamicConfigStatus=Failed` | `kubectl get asc <name> -o jsonpath='{.status.pods}' \| jq '.[].dynamicConfigStatus'` | Parameter is not dynamically changeable | Set `enableDynamicConfigUpdate: false` to force rolling restart |
| `ReadinessGateBlocking` | `kubectl get pod <pod> -o jsonpath='{.status.conditions}' \| jq '.[]'` | Readiness gate not satisfied | Check if Aerospike server is healthy inside the pod |

---

## Common Configuration Errors (CE 8.1)

| Error | Cause | Fix |
|-------|-------|-----|
| Server parse error on startup | `network.info` block present | Remove `info` block; use `admin` with port 3008 if needed |
| `data-size` too small | Below 512 MiB minimum | Set `data-size` >= 536870912 (512 MiB) |
| Server fails to start with TTL | `nsup-period=0` with `default-ttl!=0` | Set `nsup-period` to a non-zero value |
| `memory-size` not recognized | Removed in 8.x | Use `storage-engine.data-size` instead |
| `write-block-size` not recognized | Replaced in 7.1+ | Use `flush-size` instead |

---

## Useful kubectl Commands

```bash
# ===== Cluster Status =====
kubectl get asc -n <ns>                                                    # List all clusters with PHASE
kubectl get asc <name> -o jsonpath='{.status.phase}'                      # Current phase
kubectl get asc <name> -o jsonpath='{.status.phaseReason}'                # Phase reason
kubectl get asc <name> -o jsonpath='{.status.conditions}' | jq .         # All conditions
kubectl get asc <name> -o jsonpath='{.status.failedReconcileCount}'      # Circuit breaker count
kubectl get asc <name> -o jsonpath='{.status.lastReconcileError}'        # Last reconcile error

# ===== Pod Status =====
kubectl get asc <name> -o jsonpath='{.status.pods}' | jq .              # Detailed pod status
kubectl get asc <name> -o jsonpath='{.status.size}'                      # Ready pod count
kubectl get asc <name> -o jsonpath='{.status.pendingRestartPods}'        # Pods pending restart

# ===== Events =====
kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp'
kubectl get events -n <ns> -w                                             # Watch live events

# ===== Logs =====
kubectl -n aerospike-operator logs -l control-plane=controller-manager -f # Operator logs
kubectl -n <ns> logs <pod> -c aerospike-server -f                         # Aerospike server logs
kubectl -n <ns> logs <pod> -c aerospike-server --previous                 # Previous crash logs

# ===== Template =====
kubectl get asc <name> -o jsonpath='{.status.templateSnapshot.synced}'   # Template sync status
```
