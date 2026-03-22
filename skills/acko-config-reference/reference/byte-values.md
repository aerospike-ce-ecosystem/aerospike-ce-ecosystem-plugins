# Byte Values in CRD YAML

All size values in `aerospikeConfig` must be **integer byte counts**:

| Human-Readable | Integer Bytes |
|----------------|---------------|
| 128 KiB | `131072` |
| 512 MiB | `536870912` |
| 1 MiB | `1048576` |
| 1 GiB | `1073741824` |
| 2 GiB | `2147483648` |
| 4 GiB | `4294967296` |
| 8 GiB | `8589934592` |
| 16 GiB | `17179869184` |
| 32 GiB | `34359738368` |
| 64 GiB | `68719476736` |

Note: `storage.volumes[].source.persistentVolume.size` uses standard Kubernetes quantity strings (e.g., `10Gi`, `50Gi`), NOT integer bytes.
