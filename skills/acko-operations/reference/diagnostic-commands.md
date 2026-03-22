# Diagnostic Commands Quick Reference

```bash
# ===== Cluster Status =====
kubectl get asc -n <ns>                                                    # List all clusters + PHASE
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phase}'              # Current phase
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phaseReason}'        # Phase reason
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions}' | jq .  # All conditions
kubectl get asc <name> -n <ns> -o jsonpath='{.status.failedReconcileCount}'  # Circuit breaker count
kubectl get asc <name> -n <ns> -o jsonpath='{.status.lastReconcileError}'    # Last reconcile error

# ===== Pod Status =====
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq .       # Detailed pod status
kubectl get asc <name> -n <ns> -o jsonpath='{.status.size}'              # Ready pod count
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pendingRestartPods}' # Pods pending restart
kubectl get pods -n <ns> -l aerospike.io/cr-name=<name> -o wide          # Pod list with nodes

# ===== Events =====
kubectl get events -n <ns> --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp'
kubectl get events -n <ns> -w                                              # Watch events live

# ===== Logs =====
kubectl -n aerospike-operator logs -l control-plane=controller-manager -f  # Operator logs
kubectl -n <ns> logs <pod> -c aerospike-server -f                          # Aerospike server logs
kubectl -n <ns> logs <pod> -c aerospike-server --previous                  # Previous crash logs

# ===== Aerospike Server Info =====
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v status                   # Server status
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep cluster_size  # Cluster size
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep migrate       # Migration status
kubectl exec -n <ns> <pod> -c aerospike-server -- asinfo -v 'namespace/<ns-name>'    # Namespace stats

# ===== Dynamic Config Status =====
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq '.[].dynamicConfigStatus'

# ===== Template Status =====
kubectl get asc <name> -n <ns> -o jsonpath='{.status.templateSnapshot.synced}'
kubectl get events -n <ns> --field-selector reason=TemplateDrifted

# ===== PVC Status =====
kubectl get pvc -n <ns> -l aerospike.io/cr-name=<name>

# ===== Operation Status =====
kubectl get asc <name> -n <ns> -o jsonpath='{.status.operationStatus}' | jq .
```
