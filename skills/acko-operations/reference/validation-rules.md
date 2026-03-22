# Validation Rules Reference

Complete list of ACKO webhook validation errors (53) and warnings (15).

---

## Validation Errors (CR Rejected)

### Size / Image

| Rule | Error Message |
|------|--------------|
| `spec.size > 8` | `"spec.size N exceeds CE maximum of 8"` |
| `spec.size == 0` + no templateRef | `"spec.size must be set (1-8) when spec.templateRef is not specified"` |
| `spec.image` empty + no templateRef | `"spec.image must not be empty when spec.templateRef is not specified"` |
| Image contains `enterprise`/`ee-`/`ent-` | `"spec.image \"...\" is an Enterprise Edition image; only Community Edition images are allowed"` |

### Aerospike Config

| Rule | Error Message |
|------|--------------|
| `xdr` section present | `"aerospikeConfig must not contain 'xdr' section (XDR is Enterprise-only)"` |
| `tls` section present | `"aerospikeConfig must not contain 'tls' section (TLS is Enterprise-only)"` |
| namespaces > 2 | `"aerospikeConfig.namespaces count N exceeds CE maximum of 2"` |
| `heartbeat.mode != "mesh"` | `"aerospikeConfig.network.heartbeat.mode must be 'mesh' for CE"` |

### Enterprise-Only Namespace Keys (10)

The following keys are forbidden in CE namespace configuration:

`compression`, `compression-level`, `durable-delete`, `fast-restart`, `index-type`, `sindex-type`, `rack-id`, `strong-consistency`, `tomb-raider-eligible-age`, `tomb-raider-period`

Error: `"namespace[N] \"name\": 'key' is not allowed (reason)"`

### Enterprise-Only Security Keys (4)

The following keys are forbidden in CE security configuration:

`tls`, `ldap`, `log`, `syslog`

Allowed CE security keys: `enable-security`, `default-password-file`

Error: `"aerospikeConfig.security.KEY is not allowed in CE edition (reason)"`

### Namespace Validation

| Rule | Error Message |
|------|--------------|
| replication-factor < 1 or > 4 | `"namespace[N] \"name\": replication-factor must be between 1 and 4"` |
| replication-factor > spec.size | `"namespace \"name\": replication-factor N exceeds cluster size M"` |

### ACL Validation

| Rule | Error Message |
|------|--------------|
| No admin user with sys-admin + user-admin | `"aerospikeAccessControl must have at least one user with both 'sys-admin' and 'user-admin' roles"` |
| secretName empty | `"user \"name\" must have a secretName for password"` |
| Duplicate user name | `"accessControl.users: duplicate user name \"name\""` |
| Duplicate role name | `"accessControl.roles: duplicate role name \"name\""` |
| Reference to undefined role | `"user \"name\" references undefined role \"role\""` |
| Invalid privilege code | `"role \"name\" has invalid privilege code \"code\""` |
| Privilege with leading/trailing whitespace | `"role \"name\" privileges[N]: privilege string \"...\" must not have leading or trailing whitespace"` |

Valid privilege codes: `read`, `write`, `read-write`, `read-write-udf`, `sys-admin`, `user-admin`, `data-admin`, `truncate`

Privilege format: `"<code>"` / `"<code>.<namespace>"` / `"<code>.<namespace>.<set>"`

### Rack Config Validation

| Rule | Error Message |
|------|--------------|
| Rack ID <= 0 | `"rack ID must be > 0 (rack ID 0 is reserved)"` |
| Duplicate Rack ID | `"duplicate rack ID N"` |
| Duplicate rackLabel | `"duplicate rackLabel \"label\""` |
| Duplicate nodeName | `"racks[N] and racks[M] both constrained to node \"name\""` |
| Invalid IntOrString | `"rackConfig.scaleDownBatchSize must be a positive integer or percentage"` |
| Rack ID changed on update | `"rackConfig rack IDs cannot be changed"` |

### Storage Validation

| Rule | Error Message |
|------|--------------|
| Duplicate volume name | `"storage.volumes: duplicate volume name \"name\""` |
| Volume source count != 1 | `"exactly one volume source must be specified"` |
| PV size empty/invalid/negative | `"persistentVolume.size must not be empty"` / `"is not a valid Kubernetes quantity"` |
| Path not absolute | `"aerospike.path must be an absolute path"` |
| subPath + subPathExpr both set | `"subPath and subPathExpr are mutually exclusive"` |
| deleteLocalStorageOnRestart + empty localStorageClasses | `"deleteLocalStorageOnRestart is true but localStorageClasses is empty"` |

### Monitoring Validation

| Rule | Error Message |
|------|--------------|
| Port out of range | `"monitoring.port must be in range 1-65535"` |
| Port conflicts with 3000-3003 | `"monitoring.port N conflicts with Aerospike service port"` |
| exporterImage empty when enabled | `"monitoring.exporterImage must not be empty when monitoring is enabled"` |
| metricLabels contain `=` or `,` | `"monitoring.metricLabels key/value must not contain '=' or ','"` |
| customRules missing name/rules | `"customRules[N]: missing required field 'name'/'rules'"` |

### Operations Validation

| Rule | Error Message |
|------|--------------|
| More than 1 operation | `"only one operation can be specified at a time"` |
| ID length outside 1-20 chars | `"operation id must be 1-20 characters"` |
| Change during InProgress | `"cannot change operations while operation \"ID\" is InProgress"` |

### Update-Only Validation

| Rule | Error Message |
|------|--------------|
| overrides without templateRef | `"spec.overrides can only be set when spec.templateRef is specified"` |

---

## Validation Warnings (Non-Blocking)

These produce `ValidationWarning` events but do not reject the CR.

| Warning Condition | Message Summary |
|-------------------|----------------|
| Image tag missing or `latest` | Use an explicit version tag for reproducibility |
| Exporter image `latest` or no tag | Use an explicit version tag |
| `data-in-memory=true` | Memory usage may double (data cached in RAM + on disk) |
| `rollingUpdateBatchSize > spec.size` | All pods may restart simultaneously |
| `maxUnavailable >= spec.size` or `100%` | PDB provides no disruption protection |
| hostPath volume used | Not recommended for production; data is node-bound |
| cascadeDelete on non-PV volume | Has no effect on emptyDir or hostPath volumes |
| No PV for work-directory | Data loss possible on pod restart |
| hostNetwork + multiPodPerHost | Port conflicts may occur |
| hostNetwork + dnsPolicy mismatch | DNS resolution issues possible |
| serviceMonitor.enabled + monitoring.disabled | ServiceMonitor will not be created |
| prometheusRule.enabled + monitoring.disabled | PrometheusRule will not be created |
| localStorageClasses set + deleteLocalStorageOnRestart not set | Local PVCs will not be deleted on restart |
