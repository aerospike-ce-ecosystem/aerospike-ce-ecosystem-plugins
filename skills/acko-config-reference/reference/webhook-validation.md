# Webhook Validation Summary

## CE Constraints (Rejection)

The ACKO webhook rejects CRs that violate these constraints:

- `size > 8` -> rejected
- `namespaces > 2` -> rejected
- Image contains `enterprise`/`ee-`/`ent-` -> rejected
- `xdr` or `tls` section present -> rejected
- `security` present without `aerospikeAccessControl` -> rejected
- Admin user missing `sys-admin` + `user-admin` -> rejected

## Byte Values in CRD YAML

All size values in `aerospikeConfig` must be **integer byte counts**. See `reference/byte-values.md` for the full conversion table.

Note: `storage.volumes[].source.persistentVolume.size` uses standard Kubernetes quantity strings (e.g., `10Gi`, `50Gi`), NOT integer bytes.
