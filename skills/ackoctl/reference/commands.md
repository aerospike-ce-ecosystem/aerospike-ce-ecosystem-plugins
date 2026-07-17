# ackoctl command reference

Compact one-line-per-verb enumeration for constructing precise invocations. Grammar: `ackoctl <noun> <verb> [POSITIONAL] [--flag value]`. Default output `-o table`; `-o json|yaml` always available.

## `guide` — operational guides (read org/team policy first)

Read-only. **Run `guide get` before any mutating command** — data-plane before record/set/index/note writes, control-plane before connection/cluster/admin ops.

| Verb | One-liner |
|------|-----------|
| `guide list` | List guides registered for the workspace. |
| `guide get data-plane\|control-plane [--workspace WS]` | Print one guide; default = raw Markdown body, `-o json\|yaml` = structured. Falls back to `ws-default` workspace when none set. |

## `config` — context management (kubeconfig-style)

| Verb | One-liner |
|------|-----------|
| `config view` | Print merged config (tokens redacted). |
| `config current-context` | Print current context name. |
| `config use-context NAME` | Switch current context. |
| `config set-context NAME --server URL [--token TOKEN --workspace-id WS --insecure-skip-tls]` | Create/update a context. `--server` must be a well-formed `http(s)` URL with a host (validated here). |
| `config delete-context NAME` | Remove a context entry. |

## `connection` — cluster-manager connection profiles

`--host` repeatable; `--port` 1..65535. `--color` must be `#RRGGBB` hex. Duplicate `--label` keys rejected. `--password`/`--password-stdin` mutually exclusive (both optional; prefer `--password-stdin`). IDs are stable UUIDs — store them in scripts; names can change. `connection delete` cascades attached notes.

| Verb | One-liner |
|------|-----------|
| `connection list` | List profiles in the current workspace. |
| `connection get ID` | Show one profile (no password). |
| `connection create --name N --host H1 [--host H2] [--port 3000] [--color #RRGGBB] [--label k=v] [--user U (--password P \| --password-stdin)]` | Create a profile. |
| `connection update ID [--name … --host … --port … --color … --note … --label k=v …]` | Patch fields. |
| `connection delete ID --yes` | Delete a profile. |
| `connection health ID` | Probe the cluster (connected, build, edition, node/ns counts, usage). |

## `cluster` — runtime cluster inspection

| Verb | One-liner |
|------|-----------|
| `cluster info CONN_ID` | Nodes + namespaces + sets summary (raw map; use `-o json/yaml` for full payload). |
| `cluster configure-namespace CONN_ID --name NS --param KEY=VAL [--param …]` | Patch dynamic-config knobs (`--param` repeatable, ≥1 required, duplicate keys rejected, `name` reserved). |

`configure-namespace` issues `asinfo set-config` — only **runtime-mutable** knobs apply; CE cannot create namespaces at runtime (they live in `aerospike.conf`, managed by ACKO).

## `set` — set inspection + destructive ops

`set list` is derived from cluster info (no dedicated `/sets` endpoint).

| Verb | One-liner |
|------|-----------|
| `set list CONN_ID [--namespace NS]` | List sets across/within namespaces. |
| `set truncate CONN_ID --namespace NS --set S [--before-lut N] --yes` | Truncate a set (destructive). `--before-lut` (optional ns cutoff) must be positive; omit for full wipe. |

## `record` — CRUD on Aerospike records

`--pk-type` pins the particle type (`auto|string|int|bytes`); `auto` retries the alternate type on `NOT_FOUND`. `--ttl`: `-1` (never expire), `0` (namespace default), or positive seconds.

| Verb | One-liner |
|------|-----------|
| `record list CONN_ID --namespace NS [--set S] [--page-size 1..500]` | Paginated scan. |
| `record get CONN_ID --namespace NS --set S --pk PK [--pk-type auto\|string\|int\|bytes]` | Single record by PK. |
| `record put CONN_ID --namespace NS --set S --pk PK --bins '{…}' [--ttl N --pk-type …]` | Create/replace. `--bins` non-empty JSON object; `--ttl` -1\|0\|positive. |
| `record delete CONN_ID --namespace NS --set S --pk PK [--pk-type …] --yes` | Delete the record. |
| `record delete-bin CONN_ID --namespace NS --set S --pk PK --bin B [--pk-type …] --yes` | Delete one bin (removes record if last bin). |
| `record query CONN_ID --namespace NS [--set S] [--pk-pattern … --pk-match-mode exact\|prefix\|regex] [--filter '{…}'] [--predicate '{…}'] [--page ≥1 --page-size 1..500 --max-records ≥0] [--select b1,b2]` | Filtered scan. `--filter`/`--predicate` each must be a **non-empty JSON object** (arrays/scalars/`null` rejected). |

## `query` — direct query endpoint

| Verb | One-liner |
|------|-----------|
| `query exec CONN_ID --namespace NS [--set S] [--bin B --op equals\|between\|contains\|geo_within_region\|geo_contains_point --value V [--value2 V]] [--expression EXPR] [--primary-key PK --pk-type …] [--select b1,b2] [--max-records 0\|1..1000000]` | Predicate, PK lookup, or full scan. `--value2` only with `between`; barewords stay strings, `{`/`[`/`"` input must be valid JSON. |

## `index` — secondary index management

| Verb | One-liner |
|------|-----------|
| `index list CONN_ID` | List secondary indexes. |
| `index create CONN_ID --namespace NS --set S --bin B --type numeric\|string\|geo2dsphere --name NAME` | Create an index (all five flags required). |
| `index delete CONN_ID --namespace NS --name NAME --yes` | Drop an index. |

## `note` — operator annotations on sets and records

`--note` must be non-empty (whitespace-only rejected), up to 8 KB. Notes live in cluster-manager's metaDB (not Aerospike), are scoped per connection, and cascade-delete with it.

| Verb | One-liner |
|------|-----------|
| `note set update CONN_ID --namespace NS --set S --note "TEXT"` | Attach/replace a set note. |
| `note set delete CONN_ID --namespace NS --set S --yes` | Remove a set note. |
| `note set list CONN_ID [--namespace NS]` | List set notes. |
| `note record update CONN_ID --namespace NS --set S --pk PK [--pk-type …] --note "TEXT"` | Attach/replace a record note. |
| `note record delete CONN_ID --namespace NS --set S --pk PK [--pk-type …] --yes` | Remove a record note. |
| `note record list CONN_ID --namespace NS --set S` | List record notes for a slice. |

## `k8s cluster` — ACKO-managed AerospikeCluster CRs

`NS/NAME` argument; extra path segments rejected. Requires `K8S_MANAGEMENT_ENABLED=true` (else 404).

| Verb | One-liner |
|------|-----------|
| `k8s cluster list` | List clusters in the workspace. |
| `k8s cluster get NS/NAME` | Get one cluster (full CR summary). |
| `k8s cluster reconcile NS/NAME` | Force re-reconcile via annotation. |
| `k8s cluster scale NS/NAME --size 1..8 [-y]` | Scale to N nodes (CE 1..8 cap; `-y` required for scale-down, and when current size is unreadable). |
| `k8s cluster pods NS/NAME` | List pods (name, phase, ready, podIP, nodeId, rackId, image). |
| `k8s cluster logs NS/NAME --pod P [--container C --tail 1..10000 --since DUR]` | Fetch kubelet logs for one pod. |
| `k8s cluster events NS/NAME [--limit N --category C --since DUR]` | List K8s events (`--since` filtered client-side). |

## `info` — raw asinfo passthrough

| Verb | One-liner |
|------|-----------|
| `info CONN_ID --command CMD [--command CMD …] [--node NODE] [--allow-write]` | Run asinfo verbs (`--command` non-empty, repeatable); fan-out when `--node` omitted; `--allow-write` bypasses the read-only whitelist. |

Read verbs run against the cluster-manager read-only whitelist by default; mutation verbs (`set-config:`, `recluster:`, …) require `--allow-write`. Always mediated by the workspace ACL.

## `admin` — Aerospike Enterprise user + role management

CE has no security, so admin calls fail server-side (`Security is not enabled`) — a 5xx mapping to **exit code 5**; the wire is correct for EE. No `grant`/`revoke` — change roles via delete + recreate. `--password`/`--password-stdin` mutually exclusive (exactly one required).

| Verb | One-liner |
|------|-----------|
| `admin user list CONN_ID` | List users + roles + quotas. |
| `admin user create CONN_ID --username U [--roles a,b] (--password P \| --password-stdin)` | Create a user (`--roles` blank entries stripped). |
| `admin user passwd CONN_ID --username U (--password P \| --password-stdin)` | Change a user's password. |
| `admin user delete CONN_ID --username U --yes` | Delete a user. |
| `admin role list CONN_ID` | List roles + privileges. |
| `admin role create CONN_ID --name R --privilege CODE[:NS[/SET]] [--privilege …] [--whitelist CIDR,…] [--read-quota N --write-quota N]` | Create a role. Embedded extra `/` or `:` in NS/SET rejected; quotas (if set) must be positive; `--whitelist` blanks stripped. |
| `admin role delete CONN_ID --name R --yes` | Delete a role. |

## `udf` — Lua user-defined functions

| Verb | One-liner |
|------|-----------|
| `udf list CONN_ID` | List modules (filename, type=LUA, hash). |
| `udf upload CONN_ID --file ./m.lua [--filename m.lua]` | Register a Lua module (filename defaults to basename; server validates `^[a-zA-Z0-9_.-]{1,255}$`). |
| `udf remove CONN_ID --filename m.lua --yes` | Drop a module (`--filename` non-empty). |

## Global flags (apply to every verb)

| Flag | One-liner |
|------|-----------|
| `--config PATH` | Config file path (default `~/.ackoctl/config.yaml`; no env equivalent). |
| `--context NAME` | Override current context (`ACKOCTL_CONTEXT`). |
| `--server URL` | Override server base URL (`ACKOCTL_SERVER`). |
| `--token TOKEN` | Override bearer token (`ACKOCTL_TOKEN`). |
| `--workspace ID` | Override workspace ACL scope (`ACKOCTL_WORKSPACE`). |
| `-o, --output table\|json\|yaml` | Output format (validated before any API call). |
| `-v, --verbose` | Verbose logging to stderr. |
| `--insecure-skip-tls` | Skip TLS verification, dev only (`ACKOCTL_INSECURE_SKIP_TLS`). |

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | success |
| `1` | generic / config error |
| `4` | cluster-manager 4xx (bad request, auth, not-found — retry won't help) |
| `5` | cluster-manager 5xx (server / transient — retry may help) |
| `130` | aborted by signal (ctrl-c / SIGTERM) |
