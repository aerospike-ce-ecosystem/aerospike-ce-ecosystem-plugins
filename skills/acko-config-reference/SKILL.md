---
name: acko-config-reference
description: "Aerospike CE 8.1 configuration parameters, CRD YAML mapping, and ACKO operator auto-processing rules. Background reference for Aerospike cluster configuration on Kubernetes. Automatically consulted when configuring Aerospike CE 8.1 parameters, writing AerospikeCluster CRD YAML, or understanding breaking changes from 7.x to 8.1."
user-invocable: false
---

# Aerospike CE 8.1 Configuration & CRD Reference

Merged reference covering Aerospike CE 8.1 server parameters, CRD YAML mapping rules, operator auto-processing, and webhook validation. This is background knowledge for writing correct AerospikeCluster CRs.

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

## Critical Breaking Changes (Top 3)

1. **`info { port 3003 }` removed** -- causes parse error and CrashLoopBackOff. Use `admin { port 3008 }`.
2. **`memory-size` replaced by `data-size`** -- must be inside `storage-engine memory {}` block, minimum 512 MiB.
3. **`write-block-size` replaced by `flush-size`** -- internal write-block fixed at 8M in 7.1+.

Full reference: `reference/breaking-changes-7x-to-8.md`

---

## Reference Files

| Topic | File |
|-------|------|
| All breaking changes, migration diffs | `reference/breaking-changes-7x-to-8.md` |
| 8.1 parameter defaults, network ports, dynamic config commands | `reference/parameters-8.md` |
| Byte value conversion table (human-readable to integer) | `reference/byte-values.md` |
| Webhook validation rules and CE constraints | `reference/webhook-validation.md` |
| CRD-to-conf mapping, operator auto-processing, ACL config | `reference/crd-mapping.md` |

## Examples

| Example | File |
|---------|------|
| 3-node cluster with 2 namespaces (memory + device) | `examples/crd-3node-2ns.yaml` |
