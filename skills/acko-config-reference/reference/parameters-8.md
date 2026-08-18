# Aerospike CE 8.1 Parameters Reference

## 8.1 Parameters with Changed/New Defaults

The **Dynamic** column answers one question: *if I edit this key in the CR with `enableDynamicConfigUpdate: true`, does ACKO apply it with `set-config` or does it roll the pods?* It is the operator's allowlist (`internal/configdiff/dynamic_params.go`), not the server's own capability — `IsDynamic()` returns false for anything absent, and the diff engine then classifies the change static (`internal/configdiff/diff.go:145,195`).

| Parameter | Default | Dynamic in ACKO | Notes |
|-----------|---------|---------|-------|
| `max-record-size` | **1M** | **No** | 7.1+ new default. Max 8M. Not on ACKO's allowlist → editing it cold-restarts |
| `flush-size` | **1M** | No | 7.1+ replaces write-block-size. NVMe: 128K recommended |
| `data-size` | - | No | 7.0+ replaces memory-size. Specified inside storage-engine block |
| `stop-writes-sys-memory-pct` | **90** | Yes | 7.0+ replaces stop-writes-pct |
| `evict-used-pct` | **70** | **No** | Device storage utilization eviction threshold. Not on ACKO's allowlist → editing it cold-restarts |
| `evict-tenths-pct` | **5** | **No** | Eviction rate per cycle (0.5%). Not on ACKO's allowlist → editing it cold-restarts |
| `cluster-name` | (none) | No | **8.0+ strongly recommended**; prevents unintended cluster joins |
| `nsup-period` | **0** | Yes | If 0 and default-ttl != 0, **server fails to start** |

## Network Ports (8.1)

| Sub-stanza | Port | Notes |
|-----------|------|-------|
| service | 3000 | Client connections |
| fabric | 3001 | Inter-node data transfer |
| heartbeat | 3002 | Cluster heartbeat |
| **admin** | **3008** | **8.1 new** (replaces info port 3003) |

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
