# CRD YAML to aerospike.conf Mapping

The operator converts CRD YAML fields to aerospike.conf syntax automatically.

| CRD YAML | aerospike.conf |
|----------|---------------|
| `namespaces: [{ name: ns1, ... }]` | `namespace ns1 { ... }` |
| `logging: [{ name: /path }]` | `logging { file /path { ... } }` |
| `storage-engine: { type: memory, data-size: N }` | `storage-engine memory { data-size N }` |
| `storage-engine: { type: device, file: ... }` | `storage-engine device { file ... }` |
| `security: {}` | *(nothing — not rendered)* |

**`security` is dropped, not rendered.** `generateConfig` hits `case SectionSecurity: continue`
(`internal/configgen/generator.go:59-60`) and emits nothing, so no `security` stanza reaches
`aerospike.conf` however the key is written. CE has no security feature to configure, and the
webhook separately rejects the Enterprise `security` sub-keys (`tls`/`ldap`/`log`/`syslog`).

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
          result: Applied
```

**`result` is only ever `Applied`.** `reconciler_dynamic_config.go:515` is the sole writer and
hardcodes it on the success path. `Failed`, `RolledBack` and `RollbackFailed` appear in the API
doc-comment (`aerospikecluster_types.go:529`) but are never assigned; `Pending` is not even in
that list. A path that failed to apply is **absent** from the list rather than carrying a failure
value, so diagnose from the `DynamicConfigDegraded` condition (reason `RollbackFailed`),
`status.phaseReason`, and `ConfigDegradedSkip` events instead.

Inspect with:

```bash
kubectl get asc <name> -o jsonpath='{.status.pods[*].dynamicConfigChanges}' | jq
```

For phase/condition meanings (`ConfigDegraded`, `DynamicConfigDegraded`, `ReconcileHealthy`, `ReconciliationPaused`), see `conditions-and-phases.md`.
