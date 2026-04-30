# Webhook Validation Summary

> Canonical, fully-enumerated rule list (with error codes) lives at `acko-operations/reference/validation-rules.md`. This page is the **shape-and-constraints summary** for use while drafting CR YAML.

## CE Constraints (Rejection)

The ACKO webhook rejects CRs that violate these constraints:

- `size > 8` -> rejected
- `namespaces > 2` -> rejected
- Image contains `enterprise`/`ee-`/`ent-` -> rejected
- `xdr` or `tls` section present -> rejected
- `security` present without `aerospikeAccessControl` -> rejected
- Admin user missing `sys-admin` + `user-admin` -> rejected

## Strengthened map/list validation (April 2026)

The webhook now also rejects CRs that violate these structural rules — preventing permanent configgen failures from reaching the running pod:

| Field | Required shape | Common mistake |
|-------|----------------|----------------|
| `aerospikeConfig.service` | YAML map (object) | accidentally passed as string or null |
| `aerospikeConfig.network` | YAML map (object) | accidentally passed as string or null |
| `aerospikeConfig.logging` | YAML list (array) | passed as map keyed by sink name |
| `aerospikeConfig.namespaces[]` | each entry is a map with required `name` key | passed as bare string `"testns"` |
| `aerospikeConfig.namespaces[]` rack ID transitions | within one update, may add new IDs OR remove old ones, but not both | rename via add+remove in one apply (data loss risk) |
| `aerospikeConfig...metricLabels[*]` | values must be TOML-quotable: control characters (`\x00`-`\x1F`, `\x7F`) rejected | unescaped newline or tab in label value |
| `spec.operations[]` | id length 1-20; kind ∈ {`WarmRestart`, `PodRestart`}; cannot modify while one is `InProgress` | reusing an id, or editing operations spec mid-flight |
| `spec.overrides` | only valid when `spec.templateRef` is set | trying to use overrides on an inline-spec cluster |

These run at admission time, so a bad apply fails fast with a clear webhook error rather than entering CrashLoopBackOff later.

## Byte Values in CRD YAML

All size values in `aerospikeConfig` must be **integer byte counts**. See `reference/byte-values.md` for the full conversion table.

Note: `storage.volumes[].source.persistentVolume.size` uses standard Kubernetes quantity strings (e.g., `10Gi`, `50Gi`), NOT integer bytes.
