---
name: acko-deploy
description: "MUST USE for deploying Aerospike on Kubernetes. Contains CE-specific YAML templates, validated AerospikeCluster CR examples, and critical constraints that prevent enterprise-only config mistakes (feature-key-file, security sections crash CE pods). Without this skill, deployments fail on first attempt due to CE 8.1 breaking changes (data-size not memory-size, no info port 3003) or webhook map/list shape rules (service/network must be maps; logging must be a list). Triggers on: deploy/create/set up Aerospike on K8s, kind, minikube, EKS, GKE; AerospikeCluster CR; ACKO operator; helm install the ACKO operator / Cluster Manager UI / SQLite or external PostgreSQL database; spec.operations / WarmRestart / PodRestart YAML; NoSQL database on Kubernetes. 9 ready-to-use YAML examples from minimal single-node to full-featured multi-rack."
---

# ACKO Deployment Guide

Deploy Aerospike Community Edition clusters on Kubernetes using the ACKO operator.

---

## 1. Quick Deploy: 1-Node Dev Cluster in 3 Steps

### Step 1: Check Prerequisites — or Install the Operator

Operator running + CRD installed: `kubectl get pods -n aerospike-operator -l control-plane=controller-manager` and `kubectl api-resources | grep aerospikeclusters`.

**Installing the operator (Helm).** ACKO ships as an OCI Helm chart bundling operator + webhook + Cluster Manager UI (`api` + `web`), all enabled by default. cert-manager must be installed first (provisions the webhook TLS cert):

```bash
helm repo add jetstack https://charts.jetstack.io && helm repo update jetstack
helm install cert-manager jetstack/cert-manager -n cert-manager \
  --create-namespace --set crds.enabled=true --wait

helm install acko oci://ghcr.io/aerospike-ce-ecosystem/charts/aerospike-ce-kubernetes-operator \
  -n aerospike-operator --create-namespace
```

The UI `api` pod stores connection metadata (not Aerospike data). Default backend is embedded **SQLite** on a 1Gi PVC; the chart **never deploys PostgreSQL**. UI web frontend listens on 3100 (`kubectl port-forward svc/acko-aerospike-ce-kubernetes-operator-ui-web 3100:3100`).

ACKO-specific install variants:

| Goal | Flags |
|------|-------|
| Operator only, no UI | `--set ui.api.enabled=false --set ui.web.enabled=false` |
| External PostgreSQL (HA) | `--set ui.database.type=postgresql --set ui.database.postgresql.databaseUrl="postgresql://..."` (or `...existingSecret`) |
| CRDs managed separately (GitOps) | `--set crds.install=false` |

SQLite is single-writer, so the chart pins `ui.replicaCount=1` and **fails the install if raised** — use external PostgreSQL for a multi-replica UI.

**OpenTelemetry export (operator).** Off by default; needs **both** `observability.otel.enabled=true` AND a non-empty `observability.otel.endpoint` (either alone is inert / fails rendering). Exports **OTLP/gRPC only** — scheme-less `host:port` is normalized to `http://`, so pass `https://` for a TLS collector. With `networkPolicy.enabled`/`cilium.enabled`, the chart auto-adds the collector egress rule (`observability.otel.collectorPort`, default `4317`). The chart never deploys a collector. See **acko-operations** for runtime enable/verify.

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
# phase=Completed typically takes 30-90s; pod naming is <cr-name>-<rack>-<idx>
kubectl wait --for=jsonpath='{.status.phase}'=Completed asc/aerospike-basic -n aerospike --timeout=120s
kubectl get asc aerospike-basic -n aerospike
kubectl exec -n aerospike aerospike-basic-0-0 -c aerospike-server -- asinfo -v status
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
11. **Strengthened map/list shapes (April 2026)**: `aerospikeConfig.service` and `aerospikeConfig.network` must be YAML maps; `aerospikeConfig.logging` must be a YAML list; each `namespaces[]` entry must be a map with a `name` key. `MetricLabels` values are TOML-escaped — control characters are rejected. Within one update, namespace `rack-id` may be added OR removed but not both (prevents data loss on rename).
12. **Operations spec invariants**: `spec.operations[].kind` must be `WarmRestart` or `PodRestart`; `spec.operations[].id` length 1–20 chars; the operations list cannot be modified while one operation is `InProgress`. `spec.overrides` only valid when `spec.templateRef` is set.
13. **CE image minimum**: `spec.image` must be CE major ≥ 8 (e.g. `ce-7`, dotless `7`, `ce-7.x` are rejected). Tag parsing handles ported registries (`host:5000/aerospike:...`) and `@sha256:` digests.
14. **Unique namespace names**; **no Enterprise logging contexts** (`audit`, `report-data-op*`, `report-sys-admin`, `report-user-admin`, `report-violation`, `report-authentication`); `logging` entries must be maps with a non-empty `name`.
15. **ACL privilege scope**: admin codes (`sys-admin`/`user-admin`/`data-admin`) are global-only (no `.namespace`/`.set` scope); scopes on other codes must be `<ns>` or `<ns>.<set>` with no empty/extra components.
16. **Monitoring**: `serviceMonitor.interval` must be a Prometheus duration (e.g. `30s`); `serviceMonitor.labels`/`prometheusRule.labels` must be valid K8s labels.
17. **Per-rack `aerospikeConfig`** overrides are validated against the same CE constraints as cluster-level config (no CE bypass via rack override).

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

### Scenario 9: On-Demand Operations (WarmRestart / PodRestart)
- **File**: [./examples/09-operations.yaml](./examples/09-operations.yaml)
- **Use when**: You need to manually restart pods (warm via SIGUSR1, or full pod recreate) without changing spec
- **Key features**: `spec.operations[]` with `WarmRestart` (SIGUSR1) or `PodRestart` (delete+recreate); optional `podList` to target specific pods; webhook prevents modifying the operations list while one is `InProgress`

> **Monitoring sample note (`04-monitoring.yaml`)**: `metricLabels` values are TOML-escaped (double-quote-wrapped, backslash-escaped, control chars rejected); the demo `emptyDir` mounts at `/opt/aerospike/work`, not `/opt/aerospike`.

---

## 4. CR Spec Reference

Detail: `./reference/cr-spec-fields.md`

---

## 5. Webhook Auto-Settings

Webhook auto-settings and CRD field mapping: See acko-config-reference skill's `reference/crd-mapping.md`

---

## 6. Verification Commands

CR-specific status fields worth knowing — everything else is a normal `kubectl get pods/events` / `kubectl exec asinfo` flow:

```bash
kubectl get asc -n <ns>                                                                    # all clusters with phase + ready/total
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phase}'                                # current phase
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phaseReason}'                          # why (when Error / InProgress)
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions}' | jq .                    # ReconcileHealthy / DynamicConfigDegraded / etc.
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq .                          # per-pod state (rack, dynamicConfigStatus, …)
```

For systematic diagnosis when something is wrong, load the `acko-debugging` skill.

---

## 7. Byte Value Reference

Byte values: See acko-config-reference skill's `reference/byte-values.md`

---

## 8. CE 8.1 Configuration Notes

CE 8.1 notes: See acko-config-reference skill

---

## 9. Template Notes

Template-derived fields (`PodSpec.PodAntiAffinity`, `Resources`, `Storage`) reach the StatefulSet and persist across reconciles — no need to inline template values into `spec.overrides`. `VolumeClaimTemplate` updates remain immutable (VCTs are set only at StatefulSet creation time).
