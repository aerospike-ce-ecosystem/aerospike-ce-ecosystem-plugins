# CRD YAML to aerospike.conf Mapping

The operator converts CRD YAML fields to aerospike.conf syntax automatically.

| CRD YAML | aerospike.conf |
|----------|---------------|
| `namespaces: [{ name: ns1, ... }]` | `namespace ns1 { ... }` |
| `logging: [{ name: /path }]` | `logging { file /path { ... } }` |
| `storage-engine: { type: memory, data-size: N }` | `storage-engine memory { data-size N }` |
| `storage-engine: { type: device, file: ... }` | `storage-engine device { file ... }` |
| `security: {}` | `security { }` |

**Key rule**: Size values in `aerospikeConfig` are always integer bytes. The operator passes them directly to the generated config file.

---

## Operator Auto-Processing

The ACKO operator automatically sets these values when they are omitted from the CR. The three `network.*.port` values are **fixed** — the webhook rejects any other value (container ports, probes, Services and NetworkPolicies assume them); omit them or set them to exactly these defaults.

| Field | Auto-Set Value |
|-------|---------------|
| `cluster-name` | CR metadata.name |
| `network.service.port` | 3000 |
| `network.fabric.port` | 3001 |
| `network.heartbeat.port` | 3002 |
| `network.heartbeat.mode` | mesh |
| `proto-fd-max` | 15000 |
| `mesh-seed-address-port` | All pod FQDNs (auto-injected at reconciliation) |
| `access-address` | Based on aerospikeNetworkPolicy (pod IP or node IP) |

---

## ACL Configuration

```yaml
aerospikeConfig:
  security: {}                         # Enables authentication + RBAC

aerospikeAccessControl:
  users:
    - name: admin                      # Required: at least one admin
      secretName: aerospike-admin-secret
      roles: [sys-admin, user-admin]   # Both roles required
    - name: app-user
      secretName: aerospike-appuser-secret
      roles: [read-write]
```

Secret format (key must be `password`):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: aerospike-admin-secret
type: Opaque
data:
  password: YWRtaW4xMjM=              # base64-encoded password
```

---

## Status Fields (NEW: dynamicConfigChanges)

`status.pods[].dynamicConfigChanges []DynamicConfigChangeStatus` (April 2026) tracks each path mutated in the most recent dynamic config attempt. Useful for debugging which specific change failed in a 2-phase commit rollout.

```yaml
status:
  pods:
    cluster-1-0:
      dynamicConfigChanges:
        - path: service.proto-fd-max
          oldValue: "15000"
          newValue: "20000"
          result: Applied
        - path: namespaces.testns.default-ttl
          oldValue: "0"
          newValue: "3600"
          result: RolledBack       # phase 2 apply failed -> LIFO rollback succeeded
```

Per-change `result` enum: `Applied`, `Failed`, `Pending`, `RolledBack`, `RollbackFailed`.

Inspect with:

```bash
kubectl get asc <name> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' | jq
```

For phase/condition meanings (`ConfigDegraded`, `DynamicConfigDegraded`, `ReconcileHealthy`, `ReconciliationPaused`), see `conditions-and-phases.md`.
