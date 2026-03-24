# CR Spec Reference

Complete field reference for the AerospikeCluster Custom Resource.

---

## Top-Level Fields

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
| `spec.k8sNodeBlockList` | list[string] | No | Block scheduling on specific K8s nodes (for node drain) |
| `spec.seedsFinderServices.loadBalancer` | object | No | Create LoadBalancer Service for external seed discovery |

## aerospikeConfig Section

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

## Storage Section

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

## Other Sections

| Field | Type | Description |
|-------|------|-------------|
| `podSpec.aerospikeContainer.resources` | object | CPU/memory requests and limits |
| `podSpec.aerospikeContainer.securityContext` | object | Container-level security context (runAsUser, runAsGroup, privileged, readOnlyRootFilesystem, allowPrivilegeEscalation, runAsNonRoot) |
| `podSpec.readinessGateEnabled` | bool | Enable custom readiness gate `acko.io/aerospike-ready` (triggers rolling restart when toggled) |
| `rackConfig.racks[]` | list | Rack definitions with zone/node affinity |
| `rackConfig.racks[].revision` | string | Per-rack revision string; changing triggers rack-specific rolling restart |
| `rackConfig.namespaces` | list | Namespaces using rack-aware replication |
| `monitoring.enabled` | bool | Inject Prometheus exporter sidecar |
| `monitoring.serviceMonitor.enabled` | bool | Create ServiceMonitor for Prometheus Operator |
| `monitoring.env` | list[EnvVar] | Custom environment variables for exporter container |
| `monitoring.metricLabels` | map[string]string | Custom metric labels (injected via METRIC_LABELS env var) |
| `monitoring.prometheusRule` | object | Custom PrometheusRule alert definitions |
| `aerospikeAccessControl` | object | Roles and users for ACL |
| `aerospikeNetworkPolicy` | object | Access type configuration (pod/hostInternal/hostExternal) |
