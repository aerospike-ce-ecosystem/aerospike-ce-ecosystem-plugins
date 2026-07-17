# Webhook Validation Summary

> Canonical, fully-enumerated rule list (with error codes) lives at `acko-operations/reference/validation-rules.md`. This page is the **shape-and-constraints summary** for use while drafting CR YAML.

## CE Constraints (Rejection)

The ACKO webhook rejects CRs that violate these constraints:

- `size > 8` -> rejected
- `namespaces > 2` -> rejected; duplicate namespace name -> rejected
- Image contains `enterprise`/`ee-`/`ent-` or references `aerospike-server-enterprise` -> rejected; CE image major `< 8` (incl. dotless `ce-7`/`7`) -> rejected
- `xdr` or `tls` section present -> rejected
- Enterprise `security` keys (`tls`/`ldap`/`log`/`syslog`) or logging contexts (`audit`/`report-*`) -> rejected
- Admin user missing `sys-admin` + `user-admin` -> rejected
- Admin privilege (`sys-admin`/`user-admin`/`data-admin`) with a `.namespace`/`.set` scope, or a malformed scope -> rejected
- Per-rack `aerospikeConfig` override violating any CE constraint -> rejected
- `spec.overrides` content (image/size/config keys) and `AerospikeClusterTemplate` CRs are validated against the same CE constraints (template webhook registered in the chart)
- Exact error strings + full catalog: `acko-operations/reference/validation-rules.md`

## Map/list shape rules

Structural rules rejected at admission (so a bad apply fails fast instead of CrashLoopBackOff):

| Field | Required shape | Common mistake |
|-------|----------------|----------------|
| `aerospikeConfig.service` | YAML map (object) | accidentally passed as string or null |
| `aerospikeConfig.network` | YAML map (object) | accidentally passed as string or null |
| `aerospikeConfig.network.{service,heartbeat,fabric}.port` | must equal the operator's fixed ports (3000/3002/3001) — integer, not string | overriding a port (rejected: probes/Services/NetworkPolicies assume the fixed ports) |
| `aerospikeConfig.logging` | YAML list (array) | passed as map keyed by sink name |
| `aerospikeConfig.namespaces` | YAML list (array) of maps | passed as scalar or as a map keyed by namespace name |
| `aerospikeConfig.namespaces[]` | each entry is a map with required `name` key | passed as bare string `"testns"` |
| `aerospikeConfig.namespaces[]` rack ID transitions | within one update, may add new IDs OR remove old ones, but not both | rename via add+remove in one apply (data loss risk) |
| `aerospikeConfig...metricLabels[*]` | values must be TOML-quotable: control characters (`\x00`-`\x1F`, `\x7F`) rejected | unescaped newline or tab in label value |
| `spec.operations[]` | id length 1-20; kind ∈ {`WarmRestart`, `PodRestart`}; cannot modify while one is `InProgress` | reusing an id, or editing operations spec mid-flight |
| `spec.overrides` | only valid when `spec.templateRef` is set; contents CE-validated | trying to use overrides on an inline-spec cluster, or smuggling an enterprise image/size via overrides |
| `spec.templateRef` | immutable after creation | adding/removing/changing templateRef on an existing cluster |
| `spec.podSpec.sidecars[]`/`initContainers[]` names | unique, and not `aerospike-server`/`aerospike-init` | duplicating a name or shadowing a built-in container |

## Byte Values in CRD YAML

All size values in `aerospikeConfig` must be **integer byte counts**. See `reference/byte-values.md` for the full conversion table.

Note: `storage.volumes[].source.persistentVolume.size` uses standard Kubernetes quantity strings (e.g., `10Gi`, `50Gi`), NOT integer bytes.
