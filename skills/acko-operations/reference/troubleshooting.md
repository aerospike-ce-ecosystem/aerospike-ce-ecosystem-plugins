# Troubleshooting Guide

Symptom-based diagnostic reference for ACKO Aerospike clusters.

---

## Symptom-Based Diagnosis

| Symptom | Diagnostic Command | Likely Cause | Resolution |
|---------|-------------------|--------------|------------|
| Phase = `Error` | `kubectl get asc <name> -o jsonpath='{.status.lastReconcileError}'` | Invalid config, image pull failure, resource exhaustion | Read the error message, fix the root cause, re-apply the CR |
| Phase = `WaitingForMigration` | `kubectl exec <pod> -c aerospike-server -- asinfo -v 'statistics' \| tr ';' '\n' \| grep migrate` | Data migration in progress (normal during scale-down) | Wait for completion (operator auto-proceeds) |
| `InProgress` stuck > 5 min | `kubectl get pvc -n <ns> -l aerospike.io/cr-name=<name>` | PVC Pending, ImagePull failure, scheduling failure | Check StorageClass, image name, resource availability |
| `CircuitBreakerActive` event | `kubectl get asc <name> -o jsonpath='{.status.failedReconcileCount}'` | 10+ consecutive reconciliation failures | Check `lastReconcileError`, fix root cause (auto-retries with backoff) |
| Pod `CrashLoopBackOff` | `kubectl logs <pod> -c aerospike-server --previous` | Config parse error, OOM, invalid parameters | Check server logs, fix aerospikeConfig |
| Webhook rejects CR | Read `kubectl apply` error output | CE constraint violation (size>8, namespaces>2, enterprise image, xdr/tls) | Fix the CR to comply with CE constraints |
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
