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

Not installed? Install via Helm (cert-manager first, then the OCI chart):

```bash
helm repo add jetstack https://charts.jetstack.io && helm repo update jetstack
helm install cert-manager jetstack/cert-manager -n cert-manager \
  --create-namespace --set crds.enabled=true --wait

helm install acko oci://ghcr.io/aerospike-ce-ecosystem/charts/aerospike-ce-kubernetes-operator \
  -n aerospike-operator --create-namespace
```

Chart variants (operator-only, external PostgreSQL for the UI, GitOps-managed CRDs), the SQLite single-replica constraint, and operator OTel export wiring: [`./reference/helm-install.md`](./reference/helm-install.md).

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

Save as `aerospike-basic.yaml`, then `kubectl apply -f aerospike-basic.yaml`.

### Step 3: Verify

```bash
# phase=Completed typically takes 30-90s; pod naming is <cr-name>-<rack>-<idx>
kubectl wait --for=jsonpath='{.status.phase}'=Completed asc/aerospike-basic -n aerospike --timeout=120s
kubectl exec -n aerospike aerospike-basic-0-0 -c aerospike-server -- asinfo -v status
```

---

## 2. CE Constraints (Webhook-Enforced)

Violating any of these rejects the CR at apply time. The most common trip-wires:

- `spec.size` 1–8; max **2** namespaces; unique namespace names; replication-factor 1–4 integer and ≤ size.
- **No Enterprise anything**: no `xdr`/`tls` sections, no enterprise image (`enterprise`/`ee-`/`ent-`/`aerospike-server-enterprise`), CE image major ≥ 8 (`ce-7`, dotless `7` rejected), no enterprise namespace keys (`strong-consistency`, `compression`, …), security keys limited to `enable-security`/`default-password-file`, no enterprise logging contexts (`audit`, `report-*`).
- **Shapes**: `service`/`network` maps; `logging` a list; `namespaces` a list of maps each with `name`; byte values as **integer bytes** (not `"1Gi"`).
- **Fixed network ports**: service=3000, fabric=3001, heartbeat=3002 — overrides rejected; `heartbeat.mode` must be `mesh`.
- **ACL**: admin privilege codes are global-only; scopes must be `<ns>` or `<ns>.<set>`; at least one user with both `sys-admin`+`user-admin`.
- **Operations/templates**: one operation at a time (`WarmRestart`/`PodRestart`, id 1–20 chars, immutable while `InProgress`); `spec.overrides` only with `templateRef` (contents CE-validated); `templateRef` immutable; per-rack `aerospikeConfig` validated like cluster-level config.
- **Monitoring**: `serviceMonitor.interval` a Prometheus duration; labels valid K8s labels; sidecar/initContainer names unique and not `aerospike-server`/`aerospike-init`.

Canonical catalog with exact error strings: `acko-operations/reference/validation-rules.md` (same plugin). Shape-and-constraint summary for drafting YAML: `acko-config-reference/reference/webhook-validation.md`.

---

## 3. Deployment Scenarios

Each scenario is a ready-to-use YAML example in `./examples/`:

| # | File | Use when — key features |
|---|------|-------------------------|
| 1 | [01-minimal.yaml](./examples/01-minimal.yaml) | Local dev / CI — 1 node, in-memory, no persistence, no ACL |
| 2 | [02-3node-pv.yaml](./examples/02-3node-pv.yaml) | Persistence — 3 nodes, PVC-backed device storage, resource limits, cascadeDelete |
| 3 | [03-acl.yaml](./examples/03-acl.yaml) | Auth + RBAC — security stanza, admin user (sys-admin + user-admin), K8s Secrets |
| 4 | [04-monitoring.yaml](./examples/04-monitoring.yaml) | Metrics/alerting — exporter sidecar, ServiceMonitor, PrometheusRule, metric labels |
| 5 | [05-multirack.yaml](./examples/05-multirack.yaml) | Zone HA — 3 racks pinned to zones, rack-aware replication |
| 6 | [06-storage-advanced.yaml](./examples/06-storage-advanced.yaml) | Block devices, hostPath, CSI, local PV, sidecar mounts, mount propagation |
| 7 | [07-template.yaml](./examples/07-template.yaml) | Shared config — AerospikeClusterTemplate, templateRef, overrides, resync annotation |
| 8 | [08-full-featured.yaml](./examples/08-full-featured.yaml) | Production — ACL + monitoring + multi-rack + PV + PDB + dynamic config |
| 9 | [09-operations.yaml](./examples/09-operations.yaml) | Manual restarts — `spec.operations[]` WarmRestart (SIGUSR1) / PodRestart, optional `podList` |

> **Monitoring sample note (`04-monitoring.yaml`)**: `metricLabels` values are TOML-escaped (double-quote-wrapped, backslash-escaped, control chars rejected); the demo `emptyDir` mounts at `/opt/aerospike/work`, not `/opt/aerospike`.

---

## 4. CR Spec Reference

Detail: [`./reference/cr-spec-fields.md`](./reference/cr-spec-fields.md)

## 5. Webhook Auto-Settings

Auto-set values and CRD→aerospike.conf field mapping: acko-config-reference skill's `reference/crd-mapping.md`.

## 6. Verification Commands

CR-specific status fields worth knowing — everything else is a normal `kubectl get pods/events` / `kubectl exec asinfo` flow:

```bash
kubectl get asc -n <ns>                                                    # all clusters with phase + ready/total
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phase}'               # current phase
kubectl get asc <name> -n <ns> -o jsonpath='{.status.phaseReason}'         # why (when Error / InProgress)
kubectl get asc <name> -n <ns> -o jsonpath='{.status.conditions}' | jq .   # ReconcileHealthy / DynamicConfigDegraded / etc.
kubectl get asc <name> -n <ns> -o jsonpath='{.status.pods}' | jq .         # per-pod state (rack, dynamicConfigStatus, …)
```

For systematic diagnosis when something is wrong, load the `acko-debugging` skill.

## 7. Byte Values / CE 8.1 Notes

Byte-count conversion table: acko-config-reference skill's `reference/byte-values.md`. CE 8.1 parameter changes (`data-size` not `memory-size`, no `info` port block, …): acko-config-reference skill.

## 8. Template Notes

Template-derived fields (`PodSpec.PodAntiAffinity`, `Resources`, `Storage`) reach the StatefulSet and persist across reconciles — no need to inline template values into `spec.overrides`. `VolumeClaimTemplate` updates remain immutable (VCTs are set only at StatefulSet creation time).
