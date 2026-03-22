---
name: acko-config-reference
description: "Aerospike CE 8.1 configuration parameters, CRD YAML mapping, and ACKO operator auto-processing rules. Background reference for Aerospike cluster configuration on Kubernetes. Automatically consulted when configuring Aerospike CE 8.1 parameters, writing AerospikeCluster CRD YAML, or understanding breaking changes from 7.x to 8.1."
user-invocable: false
---

# Aerospike CE 8.1 Configuration & CRD Reference

Merged reference covering Aerospike CE 8.1 server parameters, CRD YAML mapping rules, operator auto-processing, and webhook validation. This is background knowledge for writing correct AerospikeCluster CRs.

---

## 7.x to 8.1 Breaking Changes

These changes cause **server startup failures** if old syntax is used. Always verify your aerospikeConfig against this list.

| Item | 7.x (Old) | 8.1 (New) | Since |
|------|-----------|-----------|-------|
| Info port | `info { port 3003 }` | **Removed**. Use `admin { port 3008 }` | 8.1.0 |
| Memory data | `memory-size 4G` | `storage-engine memory { data-size 4G }` | 7.0 deprecated, 7.1 removed |
| Write block | `write-block-size 128K` | `flush-size 128K` (internal write-block fixed at 8M) | 7.1 |
| Max record size | Default = write-block-size | **Default 1M**, max 8M | 7.1 |
| Index memory | `memory-size` (device mode) | `indexes-memory-budget` | 7.0 deprecated |
| Stop writes | `stop-writes-pct` | `stop-writes-sys-memory-pct` | 7.0 removed |
| Eviction | `high-water-memory-pct` | `evict-used-pct`, `evict-tenths-pct` | 7.0 removed |
| Data in memory | Namespace level | Inside `storage-engine device` block | 7.0 moved |
| MRT write-block | N/A | Affects data-size calculation | 8.0 |

### Migration Examples

```diff
# Memory storage engine
- namespace cache { memory-size 4G; storage-engine memory }
+ namespace cache { storage-engine memory { data-size 4G } }

# Device storage engine
- namespace data { storage-engine device { write-block-size 128K } }
+ namespace data { storage-engine device { flush-size 128K } }

# Network info port (REMOVED)
- network { info { port 3003 } }
+ network { admin { port 3008 } }
```

**Critical**: If `info {}` block remains in config, the server fails with a **parse error** and the pod enters CrashLoopBackOff.

**Minimum data-size**: 512 MiB (8 stripes * 8 write-blocks * 8 MiB = `536870912` bytes).

---

## Network Ports (8.1)

| Sub-stanza | Port | Notes |
|-----------|------|-------|
| service | 3000 | Client connections |
| fabric | 3001 | Inter-node data transfer |
| heartbeat | 3002 | Cluster heartbeat |
| **admin** | **3008** | **8.1 new** (replaces info port 3003) |

---

## 8.1 Parameters with Changed/New Defaults

| Parameter | Default | Dynamic | Notes |
|-----------|---------|---------|-------|
| `max-record-size` | **1M** | Yes | 7.1+ new default. Max 8M |
| `flush-size` | **1M** | No | 7.1+ replaces write-block-size. NVMe: 128K recommended |
| `data-size` | - | No | 7.0+ replaces memory-size. Specified inside storage-engine block |
| `stop-writes-sys-memory-pct` | **90** | Yes | 7.0+ replaces stop-writes-pct |
| `evict-used-pct` | **70** | Yes | Device storage utilization eviction threshold |
| `evict-tenths-pct` | **5** | Yes | Eviction rate per cycle (0.5%) |
| `cluster-name` | (none) | No | **8.0+ strongly recommended**; prevents unintended cluster joins |
| `nsup-period` | **0** | Yes | If 0 and default-ttl != 0, **server fails to start** |

---

## Dynamic Config Change Commands

When `enableDynamicConfigUpdate: true` is set in the CR, the operator uses these commands internally. For manual debugging:

```bash
# asinfo commands
asinfo -v "set-config:context=service;batch-index-threads=16"
asinfo -v "set-config:context=namespace;id=ns1;max-record-size=256K"

# asadm commands
asadm -e 'enable; manage config service param proto-fd-max to 100000'
asadm -e 'enable; manage config logging file /var/log/aerospike/aerospike.log param security to detail'
```

---

## K8s Deployment Checklist

Verify these items before deploying an Aerospike CE 8.1 cluster on Kubernetes.

| # | Item | Description |
|---|------|-------------|
| 1 | `mode mesh` + headless DNS | Operator auto-injects mesh-seed-address-port using pod FQDNs |
| 2 | `access-address` | Required for Smart Client partition routing (Pod/Service IP) |
| 3 | `proto-fd-max < ulimit -n` | Manage ulimit via securityContext |
| 4 | `cluster-name` explicit | Prevents unintended cluster joins |
| 5 | No `info { port 3003 }` | **8.1 parse error**. Use `admin { port 3008 }` if needed |
| 6 | `data-size >= 512 MiB` | 8 stripes * 8 write-blocks * 8 MiB minimum |
| 7 | Use `flush-size` | Not `write-block-size` (replaced in 7.1+) |
| 8 | Console logging | Enables `kubectl logs` integration |
| 9 | `nsup-period` + `default-ttl` | `nsup-period=0` + `default-ttl!=0` causes startup failure |
| 10 | CE image only | `aerospike:ce-8.1.1.1` (enterprise/ee-/ent- rejected by webhook) |

---

## Operator Auto-Processing

The ACKO operator automatically sets these values when they are omitted from the CR. You do not need to specify them unless you want non-default values.

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

## Webhook Validation Summary

### CE Constraints (Rejection)

- `size > 8` -> rejected
- `namespaces > 2` -> rejected
- Image contains `enterprise`/`ee-`/`ent-` -> rejected
- `xdr` or `tls` section present -> rejected
- `security` present without `aerospikeAccessControl` -> rejected
- Admin user missing `sys-admin` + `user-admin` -> rejected

### Byte Values in CRD YAML

All size values in `aerospikeConfig` must be **integer byte counts**:

| Human-Readable | Integer Bytes |
|----------------|---------------|
| 512 MiB | `536870912` |
| 1 GiB | `1073741824` |
| 2 GiB | `2147483648` |
| 4 GiB | `4294967296` |
| 8 GiB | `8589934592` |
| 16 GiB | `17179869184` |
| 32 GiB | `34359738368` |
| 64 GiB | `68719476736` |
| 128 KiB | `131072` |
| 1 MiB | `1048576` |

Note: `storage.volumes[].source.persistentVolume.size` uses standard Kubernetes quantity strings (e.g., `10Gi`, `50Gi`), NOT integer bytes.

---

## CRD YAML to aerospike.conf Mapping

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

## CRD Configuration Example (3 Nodes, 2 Namespaces)

```yaml
apiVersion: acko.io/v1alpha1
kind: AerospikeCluster
metadata:
  name: aerospike-cluster
  namespace: aerospike
spec:
  size: 3
  image: aerospike:ce-8.1.1.1

  aerospikeConfig:
    service:
      cluster-name: aerospike-cluster
      proto-fd-max: 15000
    network:
      service:
        address: any
        port: 3000
      heartbeat:
        mode: mesh
        port: 3002
      fabric:
        address: any
        port: 3001
    namespaces:
      - name: cache
        replication-factor: 2
        storage-engine:
          type: memory
          data-size: 4294967296          # 4 GiB
      - name: data
        replication-factor: 2
        storage-engine:
          type: device
          file: /opt/aerospike/data/data.dat
          filesize: 17179869184          # 16 GiB
          flush-size: 1048576            # 1 MiB
    logging:
      - name: /var/log/aerospike/aerospike.log
        context: any info

  storage:
    volumes:
      - name: data-vol
        source:
          persistentVolume:
            storageClass: standard
            size: 20Gi                   # K8s quantity string (NOT integer bytes)
            volumeMode: Filesystem
        aerospike:
          path: /opt/aerospike/data
        cascadeDelete: true
```
