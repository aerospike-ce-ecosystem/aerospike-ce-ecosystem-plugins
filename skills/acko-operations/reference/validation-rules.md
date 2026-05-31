# Validation Rules Reference

Canonical catalog of ACKO webhook validation errors and non-blocking warnings. The exact count grows over releases — this page is the source of truth; `acko-config-reference/reference/webhook-validation.md` is a shape-and-constraints summary that links here.

---

## Validation Errors (CR Rejected)

### Size / Image

| Rule | Error Message |
|------|--------------|
| `spec.size > 8` | `"spec.size N exceeds CE maximum of 8"` |
| `spec.size == 0` + no templateRef | `"spec.size must be set (1-8) when spec.templateRef is not specified"` |
| `spec.image` empty + no templateRef | `"spec.image must not be empty when spec.templateRef is not specified"` |
| Image contains `enterprise`/`ee-`/`ent-` | `"spec.image \"...\" is an Enterprise Edition image; only Community Edition images are allowed"` |
| CE image below major 8 (incl. dotless tags `ce-7`, `7`) | error contains `"requires Aerospike CE"` |

Image tag parsing (#321) uses the last colon after the final `/` and strips `@sha256:` digests, so enterprise/CE-version guards also apply to ported-registry (`myregistry.io:5000/aerospike:...`) and digest-pinned refs.

### Aerospike Config

| Rule | Error Message |
|------|--------------|
| `xdr` section present | `"aerospikeConfig must not contain 'xdr' section (XDR is Enterprise-only)"` |
| `tls` section present | `"aerospikeConfig must not contain 'tls' section (TLS is Enterprise-only)"` |
| namespaces > 2 | `"aerospikeConfig.namespaces count N exceeds CE maximum of 2"` |
| `heartbeat.mode != "mesh"` | `"aerospikeConfig.network.heartbeat.mode must be 'mesh' for CE"` |
| `service` not a map | `"aerospikeConfig.service must be a map"` |
| `network` not a map | `"aerospikeConfig.network must be a map"` |
| `logging` not a list | `"aerospikeConfig.logging must be a list"` |
| namespace entry not a map with `name` | `"aerospikeConfig.namespaces[N] must be a map with required key 'name'"` |
| Duplicate namespace name | `"aerospikeConfig.namespaces[N]: duplicate namespace name \"name\"; each namespace must have a unique name"` |
| Rack ID add+remove in single update (also fires when `rackConfig` is dropped entirely → implicit rack 0) | `"rackConfig: rack IDs cannot be added and removed in the same update (rename-like change risks data loss)"` |
| `MetricLabels` value contains control chars | `"monitoring.metricLabels[\"key\"]: control characters are not permitted in TOML output"` |

### Enterprise-Only Namespace Keys (10)

The following keys are forbidden in CE namespace configuration:

`compression`, `compression-level`, `durable-delete`, `fast-restart`, `index-type`, `sindex-type`, `rack-id`, `strong-consistency`, `tomb-raider-eligible-age`, `tomb-raider-period`

Error: `"namespace[N] \"name\": 'key' is not allowed (reason)"`

### Enterprise-Only Security Keys (4)

The following keys are forbidden in CE security configuration:

`tls`, `ldap`, `log`, `syslog`

Allowed CE security keys: `enable-security`, `default-password-file`

Error: `"aerospikeConfig.security.KEY is not allowed in CE edition (reason)"`

`security` must also be a map: `"aerospikeConfig.security must be a map, got T"`.

### Enterprise-Only Logging Contexts (8)

`logging` must be a list of map entries, each with a non-empty `name` key. These enterprise-only context keys are rejected on CE (they crash aerospikd at startup with "unknown context"):

`audit`, `report-data-op`, `report-data-op-user`, `report-data-op-role`, `report-sys-admin`, `report-user-admin`, `report-violation`, `report-authentication`

Error: `"aerospikeConfig.logging[N].KEY is not allowed in CE edition (reason)"`
Malformed entries: `"aerospikeConfig.logging[N] must be a map, got T"` / `"...[N] is missing the required 'name' key"` / `"...[N].name must be a non-empty string, got T"`

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
| Scope on a global-only privilege (`sys-admin`/`user-admin`/`data-admin`) | `"role \"name\" privilege \"...\": \"code\" is a global-only privilege and cannot be scoped to a namespace or set (\"scope\")"` |
| Malformed scope: empty namespace (`read.`, `read..set`) | `"role \"name\" privilege \"...\": namespace scope must not be empty"` |
| Malformed scope: empty set (`read.ns.`) | `"role \"name\" privilege \"...\": set scope must not be empty"` |
| Malformed scope: >2 components (`read.ns.set.extra`) | `"role \"name\" privilege \"...\": scope must be \"<namespace>\" or \"<namespace>.<set>\", got N components"` |

Valid privilege codes: `read`, `write`, `read-write`, `read-write-udf`, `sys-admin`, `user-admin`, `data-admin`, `truncate`

Privilege format: `"<code>"` / `"<code>.<namespace>"` / `"<code>.<namespace>.<set>"`. Admin codes (`sys-admin`/`user-admin`/`data-admin`) are global-only — they reject any scope. Unscoped+malformed scopes are caught at admission because Aerospike rejects them at role-sync time (→ `ACLSyncError`).

### Rack Config Validation

| Rule | Error Message |
|------|--------------|
| Rack ID <= 0 | `"rack ID must be > 0 (rack ID 0 is reserved)"` |
| Duplicate Rack ID | `"duplicate rack ID N"` |
| Duplicate rackLabel | `"duplicate rackLabel \"label\""` |
| Duplicate nodeName | `"racks[N] and racks[M] both constrained to node \"name\""` |
| Invalid IntOrString | `"rackConfig.scaleDownBatchSize must be a positive integer or percentage"` |
| Rack ID changed on update | `"rackConfig rack IDs cannot be changed"` |
| Per-rack `aerospikeConfig` override violates a CE constraint | `"rackConfig.racks[id=N].aerospikeConfig: <inner CE error>"` |

A rack's `aerospikeConfig` is DeepMerged into the effective config, so it is validated against the **same** CE constraints as cluster-level config (xdr/tls/security keys, >2 namespaces, mesh-only heartbeat). Prevents a CE bypass via per-rack override.

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
| `serviceMonitor.interval` not a Prometheus duration (e.g. `"5 seconds"`) | `"monitoring.serviceMonitor.interval \"...\" is not a valid Prometheus duration ..."` |
| Invalid K8s label on `serviceMonitor.labels`/`prometheusRule.labels` | `"monitoring.serviceMonitor.labels key \"k\" is not a valid Kubernetes label key: ..."` / `"...labels[\"k\"] value \"v\" is not a valid Kubernetes label value: ..."` |

These are validated because the reconciler copies them verbatim onto the ServiceMonitor/PrometheusRule; the Prometheus Operator / API server would otherwise reject them at apply time, leaving monitoring silently broken.

### MaxUnavailable Validation

| Rule | Error Message |
|------|--------------|
| `maxUnavailable` malformed (negative int, non-percentage string) | error contains `"maxUnavailable"` |

(Structural rejection at admission, in addition to the non-blocking "no disruption protection" warning below. Skipped when size is deferred to a templateRef.)

### Operations Validation

| Rule | Error Message |
|------|--------------|
| More than 1 operation | `"only one operation can be specified at a time"` |
| ID length outside 1-20 chars | `"operation id must be 1-20 characters"` |
| Invalid `kind` | `"operation kind must be one of: WarmRestart, PodRestart"` |
| Change during InProgress (incl. changing `podList`) | `"cannot change operations while operation \"ID\" is InProgress"` |

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
| `rollingUpdateBatchSize > spec.size` | All pods may restart simultaneously (suppressed when size deferred to templateRef) |
| `maxUnavailable >= spec.size` or `100%` | PDB provides no disruption protection (suppressed when size deferred to templateRef) |
| hostPath volume used | Not recommended for production; data is node-bound |
| cascadeDelete on non-PV volume | Has no effect on emptyDir or hostPath volumes |
| No PV for work-directory | Data loss possible on pod restart |
| hostNetwork + multiPodPerHost | Port conflicts may occur |
| hostNetwork + dnsPolicy mismatch | DNS resolution issues possible |
| serviceMonitor.enabled + monitoring.disabled | ServiceMonitor will not be created |
| prometheusRule.enabled + monitoring.disabled | PrometheusRule will not be created |
| localStorageClasses set + deleteLocalStorageOnRestart not set | Local PVCs will not be deleted on restart |
