# Validation Rules Reference

Canonical catalog of ACKO webhook validation errors and non-blocking warnings. The exact count grows over releases — this page is the source of truth; `acko-config-reference/reference/webhook-validation.md` is a shape-and-constraints summary that links here.

## How the messages reach you

The webhook accumulates every failure and returns them as **one** error, joined with `"; "` and prefixed with `validation failed: ` (`api/v1alpha1/aerospikecluster_webhook.go:643`). So a real `kubectl apply` rejection looks like:

```
admission webhook "vaerospikecluster.kb.io" denied the request: validation failed: spec.size 9 exceeds CE maximum of 8; aerospikeConfig.namespaces count 3 exceeds CE maximum of 2
```

When matching on these strings, match a **substring**, never the whole message: most contain `%q`/`%d` interpolations mid-string, and several rules fire together. The messages below are written with `N` / `M` / `T` / `S` / `KEY` / `FIELD` / `PATH` / `ID` / `"name"` / `'key'` / `(reason)` / `[...]` standing in for interpolated values.

---

## Validation Errors (CR Rejected)

### Size / Image

| Rule | Error Message |
|------|--------------|
| `spec.size > 8` | `"spec.size N exceeds CE maximum of 8"` |
| `spec.size == 0` + no templateRef | `"spec.size must be set (1–8) when spec.templateRef is not specified"` (note: **en dash** U+2013, not `-`) |
| `spec.image` empty + no templateRef | `"spec.image must not be empty when spec.templateRef is not specified"` |
| Image references the enterprise repo | `"spec.image \"...\" references the enterprise repository (aerospike-server-enterprise); CE clusters must use a CE image such as aerospike:ce-8.1.1.1"` |
| Image contains `enterprise`/`ee-`/`ent-` | `"spec.image \"...\" is an Enterprise Edition image; only Community Edition images are allowed"` |
| CE image below major 8 (incl. dotless tags `ce-7`, `7`) | error contains `"requires Aerospike CE"` |

Image tag parsing (#321) uses the last colon after the final `/` and strips `@sha256:` digests, so enterprise/CE-version guards also apply to ported-registry (`myregistry.io:5000/aerospike:...`) and digest-pinned refs.

### Aerospike Config

| Rule | Error Message |
|------|--------------|
| `xdr` section present | `"aerospikeConfig must not contain 'xdr' section (XDR is Enterprise-only)"` |
| top-level `tls` section present | `"aerospikeConfig must not contain 'tls' section (TLS is Enterprise-only)"` |
| nested `network.tls` section present | `"aerospikeConfig.network must not contain 'tls' section (TLS is Enterprise-only)"` |
| any `tls-*` key inside `network.{service,heartbeat,fabric}` (e.g. `tls-port`, `tls-name`, `tls-authenticate-client`) | `"aerospikeConfig.network.S.KEY is not allowed in CE edition (TLS is Enterprise-only)"` — one error per offending key, sorted |
| namespaces > 2 | `"aerospikeConfig.namespaces count N exceeds CE maximum of 2"` |
| `heartbeat.mode != "mesh"` | `"aerospikeConfig.network.heartbeat.mode must be 'mesh' for CE"` |
| `service` not a map | `"aerospikeConfig.service must be a map"` |
| `network` not a map | `"aerospikeConfig.network must be a map"` |
| `logging` not a list | `"aerospikeConfig.logging must be a list"` |
| `namespaces` a scalar (string/int/bool) | `"aerospikeConfig.namespaces must be a list of namespace maps (e.g. [{name: foo, ...}]), got T"` |
| `namespaces` a map (keyed by name) | `"aerospikeConfig.namespaces must be a list of namespace maps ..., got map with N entries; per-namespace validation cannot run on the map form"` |
| namespace entry not a map | `"aerospikeConfig.namespaces[N] must be a map, got T"` |
| namespace entry map without a `name` key | `"aerospikeConfig.namespaces[N] is missing required 'name' key"` |
| Duplicate namespace name | `"aerospikeConfig.namespaces[N]: duplicate namespace name \"name\"; each namespace must have a unique name"` |
| Rack ID add+remove in single update (also fires when `rackConfig` is dropped entirely → implicit rack 0) | `"cannot add new rack IDs [...] and remove existing rack IDs [...] in the same update; please do this in two separate steps"` — when the implicit default rack (ID 0) is involved, the message instead explains that switching between the default rack and explicit racks recreates StatefulSets and risks data loss |
| `metricLabels` value contains control chars | `"monitoring.metricLabels[\"key\"] value must not contain control characters"` |

### Network Ports (fixed by the operator)

The operator requires its fixed ports — container ports, health probes, Services and NetworkPolicies all assume them: `service`=3000, `fabric`=3001, `heartbeat`=3002 (info=3003 reserved).

| Rule | Error Message |
|------|--------------|
| Custom `network.{service,heartbeat,fabric}.port` differing from the fixed port | `"aerospikeConfig.network.S.port=N is not supported; the operator requires the fixed port M (container ports, health probes, Services and NetworkPolicies all assume it). Remove the port override or set it to M."` |
| Port collides with a *different* subsection's reserved port | `"aerospikeConfig.network.S.port=N conflicts with reserved port M (used for ...)"` |
| Port out of range | `"aerospikeConfig.network.S.port=N must be in range 1-65535"` |
| Port not an integer (e.g. `"3000"`) | `"aerospikeConfig.network.S.port must be an integer, got string \"3000\""` / `"... got T"` |

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
| replication-factor not an integer (e.g. `"2"` as string) | `"namespace \"name\": replication-factor must be an integer, got T (v)"` |
| replication-factor < 1 or > 4 | `"namespace[N] \"name\": replication-factor must be between 1 and 4"` |
| replication-factor > spec.size | `"namespace \"name\": replication-factor N exceeds cluster size M"` (skipped when size is deferred to a templateRef) |

### ACL Validation

| Rule | Error Message |
|------|--------------|
| No admin user with sys-admin + user-admin | `"aerospikeAccessControl must have at least one user with both 'sys-admin' and 'user-admin' roles"` |
| secretName empty | `"user \"name\" must have a secretName for password"` |
| Duplicate user name | `"accessControl.users: duplicate user name \"name\""` |
| Duplicate role name | `"accessControl.roles: duplicate role name \"name\""` |
| Empty role name in role definitions | `"accessControl.roles[N]: role name must not be empty"` |
| Empty role name in a user's `roles[]` | `"user \"name\" roles[N]: role name must not be empty"` |
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
| Rack ID <= 0 | `"rack ID must be > 0, got N (rack ID 0 is reserved for the default rack)"` |
| Duplicate Rack ID | `"duplicate rack ID N in rackConfig"` |
| Duplicate rackLabel | `"duplicate rackLabel \"label\" in rackConfig; each rack must have a unique rackLabel"` |
| `scaleDownBatchSize` / `maxIgnorablePods` / `rollingUpdateBatchSize` below their minimum | `"rackConfig.FIELD must be a positive integer (got N)"` (`maxIgnorablePods` says `non-negative`) |
| …given a string that is not a percentage | `"rackConfig.FIELD must be a positive integer or a percentage string (e.g., \"25%\"); got \"...\""` |
| …given a percentage outside range | `"rackConfig.FIELD percentage must be between MIN and 100 (got N)"` / `"rackConfig.FIELD percentage \"...\" is not a valid integer"` |
| More racks than `spec.size` | `"rackConfig defines N racks but spec.size is M; each rack must get at least 1 pod, so the rack count must not exceed spec.size"` (skipped when size deferred to templateRef) |
| Per-rack `aerospikeConfig` override violates a CE constraint | `"rackConfig.racks[id=N].aerospikeConfig: <inner CE error>"` |

`MIN` is 1 for `scaleDownBatchSize` and `rollingUpdateBatchSize`, 0 for `maxIgnorablePods` — the same `validateIntOrString` helper (`aerospikecluster_webhook.go:1637-1664`) also produces the `maxUnavailable` messages, with field name `maxUnavailable` and `MIN` 0.

A rack's `aerospikeConfig` is DeepMerged into the effective config, so it is validated against the **same** CE constraints as cluster-level config (xdr/tls/security keys, >2 namespaces, mesh-only heartbeat). Prevents a CE bypass via per-rack override.

**Rack IDs are mutable, and `nodeName` is not validated.** Two rules that sound plausible are *not* enforced — do not refuse an operation on their account:

- **Rack IDs can be changed.** `ValidateUpdate` blocks only the *simultaneous* add-and-remove case (the row in [Aerospike Config](#aerospike-config) above); a pure addition or a pure removal is accepted (`aerospikecluster_webhook.go:308-350`). Renaming rack `1` to `2` is legal as two applies: add `2`, then remove `1`.
- **Two racks may share a `nodeName`.** `Rack.NodeName` is never checked by `validateRackConfig` (`aerospikecluster_webhook.go:1549-1611`) — it validates rack ID, `rackLabel`, the IntOrString fields, and the per-rack `aerospikeConfig`, and nothing else. Sharing a node across racks is the normal shape for preferred (soft) anti-affinity, and the operator has a regression test asserting it is accepted (`webhook_test.go:3844-3862`).

### PodSpec Container Names

`spec.podSpec.sidecars[]` / `spec.podSpec.initContainers[]` names are validated:

| Rule | Error Message |
|------|--------------|
| Name collides with operator built-ins (`aerospike-server`, `aerospike-init`) | `"spec.podSpec.sidecars[N] name \"...\" conflicts with operator built-in container name"` (same for `initContainers[N]`) |
| Duplicate within sidecars / within initContainers | `"spec.podSpec.sidecars[N] name \"...\" duplicates sidecars[M]"` / `"...initContainers[N] ... duplicates initContainers[M]"` |
| initContainer name duplicates a sidecar | `"spec.podSpec.initContainers[N] name \"...\" duplicates sidecars[M]"` |

### Storage Validation

| Rule | Error Message |
|------|--------------|
| Duplicate volume name | `"storage.volumes: duplicate volume name \"name\""` |
| Duplicate `containerName` in a volume's `sidecars[]`/`initContainers[]` attachments (incl. cross: initContainer vs sidecar) | `"storage.volumes[N] \"vol\": sidecars[i] containerName \"...\" duplicates sidecars[j]"` (same pattern for `initContainers`) |
| Volume source count != 1 | `"exactly one volume source must be specified"` |
| PV size empty/invalid/negative | `"persistentVolume.size must not be empty"` / `"is not a valid Kubernetes quantity"` |
| Path not absolute | `"aerospike.path must be an absolute path"` |
| subPath + subPathExpr both set | `"subPath and subPathExpr are mutually exclusive"` |
| deleteLocalStorageOnRestart + empty localStorageClasses | `"storage.deleteLocalStorageOnRestart is true but storage.localStorageClasses is empty; specify which storage classes are local"` |

### Monitoring Validation

| Rule | Error Message |
|------|--------------|
| Port out of range | `"monitoring.port must be in range 1-65535"` |
| Port conflicts with 3000-3003 | `"monitoring.port N conflicts with Aerospike S port"` — `S` is the reserved port's name: `service` (3000), `fabric` (3001), `heartbeat` (3002), `info` (3003) |
| exporterImage empty when enabled | `"monitoring.exporterImage must not be empty when monitoring is enabled"` |
| metricLabels **key** outside `^[A-Za-z0-9_-]+$` | `"monitoring.metricLabels key \"k\" must contain only ASCII letters, digits, dashes, and underscores"` |
| customRules missing name/rules | `"monitoring.prometheusRule.customRules[N]: missing required field 'name'"` / `"... missing required field 'rules'"` |
| customRules value is not valid JSON | `"monitoring.prometheusRule.customRules[N]: invalid JSON: ..."` |
| customRules `name` not a string / empty | `"monitoring.prometheusRule.customRules[N]: field 'name' must be a string, got T"` / `"... must not be empty"` |
| customRules `rules` not a JSON array / empty array | `"monitoring.prometheusRule.customRules[N]: field 'rules' must be a JSON array, got T"` / `"... must contain at least one rule"` |
| `serviceMonitor.interval` not a Prometheus duration (e.g. `"5 seconds"`) | `"monitoring.serviceMonitor.interval \"...\" is not a valid Prometheus duration ..."` |
| Invalid K8s label on `serviceMonitor.labels`/`prometheusRule.labels` | `"PATH key \"k\" is not a valid Kubernetes label key: ..."` / `"PATH[\"k\"] value \"v\" is not a valid Kubernetes label value: ..."` — `PATH` is the dotted CR path the caller passes, i.e. `monitoring.serviceMonitor.labels` or `monitoring.prometheusRule.labels` |

These are validated because the reconciler copies them verbatim onto the ServiceMonitor/PrometheusRule; the Prometheus Operator / API server would otherwise reject them at apply time, leaving monitoring silently broken.

**`=` and `,` are legal inside `metricLabels` values.** The constraint is TOML compatibility, and the operator quotes values before writing them, so only the *key* charset is restricted (`^[A-Za-z0-9_-]+$`, `aerospikecluster_webhook.go:44`) and only control characters are rejected in values (`:1964-1978`). `metricLabels: {env: "a=b,c"}` is accepted; `metricLabels: {"env.tier": "prod"}` is not.

### MaxUnavailable Validation

| Rule | Error Message |
|------|--------------|
| `maxUnavailable` malformed (negative int, non-percentage string) | error contains `"maxUnavailable"` |

(Structural rejection at admission, in addition to the non-blocking "no disruption protection" warning below. Skipped when size is deferred to a templateRef.)

### Operations Validation

| Rule | Error Message |
|------|--------------|
| More than 1 operation | `"only one operation can be specified at a time"` |
| ID length outside 1-20 chars | `"operation id \"ID\" must be 1-20 characters"` |
| Duplicate operation id | `"duplicate operation id \"ID\""` |
| Change during InProgress (incl. changing `podList`) | `"cannot change operations while operation \"ID\" is InProgress"` |

An invalid `kind` is **not** a webhook error. `OperationKind` carries `+kubebuilder:validation:Enum=WarmRestart;PodRestart` (`api/v1alpha1/aerospikecluster_types.go:119-127`), so the API server rejects it from the CRD's OpenAPI schema before the webhook runs, with the standard shape:

```
spec.operations[0].kind: Unsupported value: "Foo": supported values: "WarmRestart", "PodRestart"
```

That message has no `validation failed: ` prefix — it is not produced by ACKO.

### Template / Overrides Validation

`spec.overrides` **contents** are validated against the same CE constraints (not just presence-with-templateRef):

| Rule | Error Message |
|------|--------------|
| `overrides.image` enterprise repo/tag | `"spec.overrides.image \"...\" references the enterprise repository (aerospike-server-enterprise); CE clusters must use a CE image such as aerospike:ce-8.1.1.1"` / `"... is an Enterprise Edition image; only Community Edition images are allowed"` |
| `overrides.size` outside 1–8 | `"spec.overrides.size N must be between 1 and 8 (CE limit)"` |
| Enterprise keys in `overrides.aerospikeConfig.namespaceDefaults` / `.service` | banned-key errors carrying those field-path prefixes (xdr / tls / EE security keys / EE namespace keys) |

The **AerospikeClusterTemplate CR** has its own admission webhook (registered in the Helm chart, `failurePolicy: Fail`): enterprise image, `spec.size` outside 1–8, `spec.monitoring.port` outside 1–65535, and enterprise keys in `spec.aerospikeConfig.namespaceDefaults`/`.service` are all rejected at template-apply time. As defence-in-depth, the resolver re-validates the post-merge spec at reconcile time (`"resolved spec violates CE constraints after applying template \"...\": ..."`).

### Update-Only Validation

| Rule | Error Message |
|------|--------------|
| overrides without templateRef | `"spec.overrides can only be set when spec.templateRef is specified"` |
| `templateRef` **added** on update | `"spec.templateRef is immutable: cannot add templateRef to an existing cluster; create a new cluster that references the template"` |
| `templateRef` **removed** on update | `"spec.templateRef is immutable: cannot remove templateRef from a cluster that was created with one (was \"name\")"` |
| `templateRef` **changed** on update | `"spec.templateRef is immutable: cannot change templateRef from \"a\" to \"b\"; create a new cluster instead"` |

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
