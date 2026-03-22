---
name: acko-deploy
description: "MUST USE for deploying Aerospike on Kubernetes. Contains CE-specific YAML templates, validated AerospikeCluster CR examples, and critical constraints that prevent enterprise-only config mistakes (feature-key-file, security sections crash CE pods). Without this skill, deployments fail on first attempt due to CE 8.1 breaking changes (data-size not memory-size, no info port 3003). Triggers on: deploy/create/set up Aerospike on K8s, kind, minikube, EKS, GKE; AerospikeCluster CR; ACKO operator; Aerospike cluster YAML; NoSQL database on Kubernetes. This skill has 8 ready-to-use YAML examples from minimal single-node to full-featured multi-rack with monitoring."
---

# ACKO Deployment Guide

Deploy Aerospike Community Edition clusters on Kubernetes using the ACKO operator.

---

## 1. Quick Deploy: 1-Node Dev Cluster in 3 Steps

### Step 1: Check Prerequisites

Run these commands to verify your environment is ready:

```bash
# Verify kubectl is connected to a cluster
kubectl cluster-info

# Verify the ACKO operator is running
kubectl get pods -n aerospike-operator -l control-plane=controller-manager

# Verify the AerospikeCluster CRD is installed
kubectl api-resources | grep aerospikeclusters

# Create the target namespace (if it does not exist)
kubectl create namespace aerospike --dry-run=client -o yaml | kubectl apply -f -
```

If the operator is not running, install it first:
```bash
kubectl apply -f https://raw.githubusercontent.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator/main/config/deploy/operator.yaml
```

### Step 2: Apply the Minimal CR

```yaml
apiVersion: acko.io/v1alpha1
kind: AerospikeCluster
metadata:
  name: aerospike-basic
  namespace: aerospike
spec:
  size: 1
  image: aerospike:ce-8.1.1.1
  aerospikeConfig:
    namespaces:
      - name: test
        replication-factor: 1
        storage-engine:
          type: memory
          data-size: 1073741824   # 1 GiB
    logging:
      - name: /var/log/aerospike/aerospike.log
        context: any info
```

Save this as `aerospike-basic.yaml` and apply:
```bash
kubectl apply -f aerospike-basic.yaml
```

### Step 3: Verify Deployment

```bash
# Wait for phase=Completed (typically 30-90 seconds)
kubectl wait --for=jsonpath='{.status.phase}'=Completed asc/aerospike-basic -n aerospike --timeout=120s

# Check cluster status (should show PHASE=Completed, HEALTH=1/1)
kubectl get asc aerospike-basic -n aerospike

# Check pod status (should show 1/1 Running)
kubectl get pods -n aerospike

# Verify Aerospike is responding
kubectl exec -n aerospike aerospike-basic-0-0 -c aerospike-server -- asinfo -v status
# Expected output: ok
```

---

## 2. CE Constraints (Webhook-Enforced)

These constraints are enforced by the ACKO validating webhook. Violating any of them causes the CR to be rejected at apply time.

1. **Cluster size**: `spec.size` must be between 1 and 8 (inclusive).
2. **Namespaces**: Maximum 2 namespaces in `aerospikeConfig.namespaces`.
3. **No XDR**: `aerospikeConfig` must not contain an `xdr` section (Enterprise-only).
4. **No TLS**: `aerospikeConfig` must not contain a `tls` section (Enterprise-only).
5. **No Enterprise images**: `spec.image` must not contain `enterprise`, `ee-`, or `ent-`.
6. **Mesh heartbeat only**: `network.heartbeat.mode` must be `mesh`.
7. **Byte values as integers**: All size values in `aerospikeConfig` (such as `data-size`, `filesize`) must be specified as integer byte counts, not human-readable strings.
8. **Replication factor**: Must be between 1 and 4, and must not exceed `spec.size`.
9. **No Enterprise namespace keys**: The following keys are forbidden in namespace config: `compression`, `compression-level`, `durable-delete`, `fast-restart`, `index-type`, `sindex-type`, `rack-id`, `strong-consistency`, `tomb-raider-eligible-age`, `tomb-raider-period`.
10. **No Enterprise security keys**: Only `enable-security` and `default-password-file` are allowed in `aerospikeConfig.security`. The keys `tls`, `ldap`, `log`, `syslog` are forbidden.

---

## 3. Deployment Scenarios

Choose the scenario that matches your needs. Each links to a ready-to-use YAML example.

### Scenario 1: Minimal In-Memory (Dev/Test)
- **File**: [./examples/01-minimal.yaml](./examples/01-minimal.yaml)
- **Use when**: Quick local dev, CI tests, learning ACKO
- **Key features**: 1 node, in-memory storage, no persistence, no ACL

### Scenario 2: 3-Node with Persistent Volume (Staging/Production Baseline)
- **File**: [./examples/02-3node-pv.yaml](./examples/02-3node-pv.yaml)
- **Use when**: You need data persistence across pod restarts
- **Key features**: 3 nodes, PVC-backed device storage, resource limits, cascadeDelete

### Scenario 3: ACL (Access Control)
- **File**: [./examples/03-acl.yaml](./examples/03-acl.yaml)
- **Use when**: You need authentication and role-based access control
- **Key features**: security stanza, admin user (sys-admin + user-admin required), K8s Secrets for passwords

### Scenario 4: Prometheus Monitoring
- **File**: [./examples/04-monitoring.yaml](./examples/04-monitoring.yaml)
- **Use when**: You need metrics, dashboards, and alerting
- **Key features**: Exporter sidecar, ServiceMonitor, PrometheusRule, metric labels

### Scenario 5: Multi-Rack (Zone-Aware Topology)
- **File**: [./examples/05-multirack.yaml](./examples/05-multirack.yaml)
- **Use when**: You need high availability across availability zones
- **Key features**: 3 racks pinned to zones, rack-aware replication

### Scenario 6: Advanced Storage
- **File**: [./examples/06-storage-advanced.yaml](./examples/06-storage-advanced.yaml)
- **Use when**: You need block devices, hostPath, CSI, local PV, or sidecar mounts
- **Key features**: Volume policies, block volumes, mount propagation, sidecar sharing

### Scenario 7: Template-Based
- **File**: [./examples/07-template.yaml](./examples/07-template.yaml)
- **Use when**: You manage multiple clusters with shared configuration
- **Key features**: AerospikeClusterTemplate, templateRef, overrides, resync annotation

### Scenario 8: Full-Featured
- **File**: [./examples/08-full-featured.yaml](./examples/08-full-featured.yaml)
- **Use when**: Production deployment with all features enabled
- **Key features**: ACL + monitoring + multi-rack + PV + PDB + dynamic config

---

## 4. CR Spec Reference

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec.size` | int | Yes | Number of Aerospike server pods (CE: 1-8) |
| `spec.image` | string | Yes | Aerospike CE container image (e.g., `aerospike:ce-8.1.1.1`) |
| `spec.paused` | bool | No | Set `true` to pause all reconciliation |
| `spec.enableDynamicConfigUpdate` | bool | No | Apply config changes without pod restart |
| `spec.rollingUpdateBatchSize` | int/string | No | Pods to restart per batch (default: 1, or "25%") |
| `spec.disablePDB` | bool | No | Set `true` to skip PodDisruptionBudget creation |
| `spec.maxUnavailable` | int/string | No | PDB maxUnavailable value (default: 1) |
| `spec.templateRef.name` | string | No | Reference an AerospikeClusterTemplate |
| `spec.overrides` | object | No | Override template fields (only with templateRef) |
| `spec.operations` | list | No | On-demand operations (WarmRestart, PodRestart) |

### aerospikeConfig Section

| Field | Type | Description |
|-------|------|-------------|
| `service.cluster-name` | string | Cluster name (auto-set to CR name if omitted) |
| `service.proto-fd-max` | int | Max client connections (auto-set to 15000 if omitted) |
| `network.service.port` | int | Service port (auto-set to 3000 if omitted) |
| `network.heartbeat.mode` | string | Must be `mesh` for CE on K8s (auto-set if omitted) |
| `network.heartbeat.port` | int | Heartbeat port (auto-set to 3002 if omitted) |
| `network.fabric.port` | int | Fabric port (auto-set to 3001 if omitted) |
| `namespaces` | list | Namespace definitions (CE: max 2) |
| `namespaces[].storage-engine.type` | string | `memory` or `device` |
| `namespaces[].storage-engine.data-size` | int | Memory size in bytes (for type: memory) |
| `namespaces[].storage-engine.filesize` | int | Data file size in bytes (for type: device) |
| `security` | object | Enable ACL (requires aerospikeAccessControl) |
| `logging` | list | Log file paths and context levels |

### Storage Section

| Field | Type | Description |
|-------|------|-------------|
| `storage.volumes[]` | list | Volume definitions |
| `storage.volumes[].name` | string | Unique volume name |
| `storage.volumes[].source.persistentVolume` | object | PVC-backed volume |
| `storage.volumes[].source.emptyDir` | object | Ephemeral volume |
| `storage.volumes[].source.hostPath` | object | Host path volume (dev only) |
| `storage.volumes[].aerospike.path` | string | Absolute mount path in container |
| `storage.volumes[].cascadeDelete` | bool | Delete PVC when CR is deleted |
| `storage.filesystemVolumePolicy` | object | Global policy for filesystem volumes |
| `storage.blockVolumePolicy` | object | Global policy for block volumes |

### Other Sections

| Field | Type | Description |
|-------|------|-------------|
| `podSpec.aerospikeContainer.resources` | object | CPU/memory requests and limits |
| `rackConfig.racks[]` | list | Rack definitions with zone/node affinity |
| `rackConfig.namespaces` | list | Namespaces using rack-aware replication |
| `monitoring.enabled` | bool | Inject Prometheus exporter sidecar |
| `monitoring.serviceMonitor.enabled` | bool | Create ServiceMonitor for Prometheus Operator |
| `aerospikeAccessControl` | object | Roles and users for ACL |
| `aerospikeNetworkPolicy` | object | Access type configuration (pod/hostInternal/hostExternal) |

---

## 5. Webhook Auto-Settings

The ACKO webhook automatically sets these fields if you omit them. You do not need to specify them unless you want non-default values.

| Field | Auto-Set Value |
|-------|---------------|
| `service.cluster-name` | CR metadata.name |
| `service.proto-fd-max` | 15000 |
| `network.service.port` | 3000 |
| `network.fabric.port` | 3001 |
| `network.heartbeat.port` | 3002 |
| `network.heartbeat.mode` | mesh |
| `monitoring.exporterImage` | `aerospike/aerospike-prometheus-exporter:1.16.1` |
| `monitoring.port` | 9145 |
| `mesh-seed-address-port` | All pod FQDNs (auto-injected) |
| `access-address` | Based on aerospikeNetworkPolicy (pod/node IP) |

---

## 6. Verification Commands

Run these after deploying or modifying a cluster.

```bash
# List all Aerospike clusters with their phase
kubectl get asc -n aerospike

# Check specific cluster phase
kubectl get asc <name> -n aerospike -o jsonpath='{.status.phase}'

# Check phase reason (useful when phase is Error or InProgress)
kubectl get asc <name> -n aerospike -o jsonpath='{.status.phaseReason}'

# Check all conditions
kubectl get asc <name> -n aerospike -o jsonpath='{.status.conditions}' | jq .

# Check pod status details
kubectl get asc <name> -n aerospike -o jsonpath='{.status.pods}' | jq .

# Check ready pod count
kubectl get asc <name> -n aerospike -o jsonpath='{.status.size}'

# Check cluster events (most recent last)
kubectl get events -n aerospike --field-selector involvedObject.name=<name> --sort-by='.lastTimestamp'

# Verify Aerospike service is responding
kubectl exec -n aerospike <pod-name> -c aerospike-server -- asinfo -v status

# Check cluster membership
kubectl exec -n aerospike <pod-name> -c aerospike-server -- asinfo -v 'statistics' | tr ';' '\n' | grep cluster_size

# Check namespace stats
kubectl exec -n aerospike <pod-name> -c aerospike-server -- asinfo -v 'namespace/<namespace-name>'
```

---

## 7. Byte Value Reference

All size values in `aerospikeConfig` must be specified as integer byte counts. Use this table for conversion.

| Human-Readable | Bytes (Integer Value) |
|----------------|----------------------|
| 512 MiB | `536870912` |
| 1 GiB | `1073741824` |
| 2 GiB | `2147483648` |
| 4 GiB | `4294967296` |
| 8 GiB | `8589934592` |
| 16 GiB | `17179869184` |
| 32 GiB | `34359738368` |
| 40 GiB | `42949672960` |
| 50 GiB | `53687091200` |
| 64 GiB | `68719476736` |
| 100 GiB | `107374182400` |
| 128 KiB | `131072` |
| 1 MiB | `1048576` |

**Formula**: GiB value * 1073741824 = bytes. MiB value * 1048576 = bytes.

**Important**: The minimum `data-size` for a memory storage engine is 512 MiB (`536870912` bytes), calculated as 8 stripes * 8 write-blocks * 8 MiB.

---

## 8. CE 8.1 Configuration Notes

When writing `aerospikeConfig` for CE 8.1, be aware of these breaking changes from older versions:

- **No `info` port block**: Do not include `network.info`. Use `network.admin` with port 3008 if needed. Including `info` causes a server parse error and pod crash.
- **Use `data-size` not `memory-size`**: For `storage-engine.type: memory`, use `data-size` (integer bytes). The old `memory-size` is removed in 8.x.
- **Use `flush-size` not `write-block-size`**: For `storage-engine.type: device`, use `flush-size`. Default is 1 MiB. For NVMe, 128 KiB is recommended.
- **`stop-writes-sys-memory-pct`**: Replaces the old `stop-writes-pct`. Default is 90.
- **`nsup-period` and `default-ttl`**: If `default-ttl` is non-zero, `nsup-period` must also be non-zero, or the server fails to start.
