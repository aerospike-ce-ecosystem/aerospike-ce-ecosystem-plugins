# ackoctl command reference

Compact one-line-per-verb enumeration. Use this when constructing a precise `ackoctl` invocation — the SKILL.md prose covers semantics; this file covers exact verbs and flags. Grammar is uniform: `ackoctl <noun> <verb> [POSITIONAL] [--flag value]`. Default output is `-o table`; `-o json|yaml` is always available.

## `config` — context management (kubeconfig-style)

| Verb | One-liner |
|------|-----------|
| `config view` | Print the merged config (~/.ackoctl/config.yaml). |
| `config use-context NAME` | Switch the current context. |
| `config set-context NAME --server URL --token TOKEN [--workspace WS]` | Create/update a context entry. |
| `config delete-context NAME` | Remove a context entry. |

## `connection` — cluster-manager connection profiles

| Verb | One-liner |
|------|-----------|
| `connection list` | List connection profiles in the current workspace. |
| `connection get ID` | Show a single profile (no password). |
| `connection create --name N --hosts H1,H2 --port 3000 [--username U --password P]` | Create a profile. |
| `connection update ID [--name ... --hosts ... --color ... --note ...]` | Patch fields. |
| `connection delete ID --yes` | Delete a profile. |
| `connection connect ID` | Force the profile to (re)open its aerospike-py client. |
| `connection disconnect ID` | Close the open client. |
| `connection test --hosts H1 --port 3000 [--username U --password P]` | Dry-run a connect attempt without persisting. |

## `cluster` — runtime cluster inspection

| Verb | One-liner |
|------|-----------|
| `cluster info CONN_ID` | Nodes + namespaces + sets summary. |
| `cluster configure-namespace CONN_ID --namespace NS --set KEY=VAL [...]` | Patch dynamic-config knobs server-side. |

## `set` — set inspection + destructive ops

| Verb | One-liner |
|------|-----------|
| `set list CONN_ID [--namespace NS]` | List sets across (or within) namespaces. |
| `set truncate CONN_ID --namespace NS --set S [--before-lut NS] --yes` | Truncate a whole set (destructive; --before-lut is optional ns cutoff). |

## `record` — CRUD on Aerospike records

| Verb | One-liner |
|------|-----------|
| `record list CONN_ID --namespace NS [--set S] [--page-size N]` | Paginated scan. |
| `record get CONN_ID --namespace NS --set S --pk PK [--pk-type auto\|string\|int\|bytes]` | Single record by primary key. |
| `record put CONN_ID --namespace NS --set S --pk PK --bins '{"k":"v"}' [--ttl N --pk-type ...]` | Create or replace. |
| `record delete CONN_ID --namespace NS --set S --pk PK [--pk-type ...] --yes` | Delete the whole record. |
| `record delete-bin CONN_ID --namespace NS --set S --pk PK --bin B [--pk-type ...] --yes` | Delete a single bin (removes record if last bin). |
| `record query CONN_ID --namespace NS [--set S --filter JSON --pk-pattern ...]` | Filtered scan with optional predicate. |

## `query` — direct query endpoint

| Verb | One-liner |
|------|-----------|
| `query CONN_ID --namespace NS [--set S --filter JSON --page-size N]` | Same shape as `record query` against the explicit query endpoint. |

## `index` — secondary index management

| Verb | One-liner |
|------|-----------|
| `index list CONN_ID [--namespace NS]` | List secondary indexes. |
| `index create CONN_ID --namespace NS --set S --bin B --type numeric\|string\|geo2dsphere --name NAME` | Create a secondary index. |
| `index delete CONN_ID --namespace NS --name NAME --yes` | Drop an index. |

## `note` — operator annotations on sets and records

| Verb | One-liner |
|------|-----------|
| `note set update CONN_ID --namespace NS --set S --note "TEXT"` | Attach/replace a set-level note. |
| `note set delete CONN_ID --namespace NS --set S --yes` | Remove a set note. |
| `note set list CONN_ID [--namespace NS]` | List set notes (optionally scoped). |
| `note record update CONN_ID --namespace NS --set S --pk PK [--pk-type ...] --note "TEXT"` | Attach/replace a record note. |
| `note record delete CONN_ID --namespace NS --set S --pk PK [--pk-type ...] --yes` | Remove a record note. |
| `note record list CONN_ID --namespace NS --set S` | List record notes for a slice. |

## `k8s cluster` — ACKO-managed AerospikeCluster CRs

| Verb | One-liner |
|------|-----------|
| `k8s cluster list` | List clusters in the workspace. |
| `k8s cluster get NS/NAME` | Get one cluster (full CR summary). |
| `k8s cluster reconcile NS/NAME` | Force ACKO to re-reconcile by setting an annotation. |
| `k8s cluster scale NS/NAME --size N [-y]` | Scale to N nodes (1..8 CE cap); `-y` required for scale-down. |
| `k8s cluster pods NS/NAME` | List pods (name, phase, ready, podIP, nodeId, rackId, image). |
| `k8s cluster logs NS/NAME --pod P [--container C --tail N --since DUR]` | Fetch kubelet logs for one pod. |
| `k8s cluster events NS/NAME [--limit N --category C --since DUR]` | List K8s events (client-side --since filter). |

## `info` — raw asinfo passthrough

| Verb | One-liner |
|------|-----------|
| `info CONN_ID --command CMD [--command CMD ...] [--node NODE] [--allow-write]` | Run one or more asinfo verbs; fan-out across nodes when --node omitted; --allow-write bypasses the read-only whitelist. |

## `admin` — Aerospike Enterprise user + role management

CE has no security; admin commands always 5xx against CE targets but the wire is correct for EE.

| Verb | One-liner |
|------|-----------|
| `admin user list CONN_ID` | List Aerospike users + their roles + quotas. |
| `admin user create CONN_ID --username U [--roles a,b] (--password P \| --password-stdin)` | Create a user. |
| `admin user passwd CONN_ID --username U (--password P \| --password-stdin)` | Change a user's password. |
| `admin user delete CONN_ID --username U --yes` | Delete a user. |
| `admin role list CONN_ID` | List roles + privileges. |
| `admin role create CONN_ID --name R --privilege CODE[:NS[/SET]] [--privilege ...] [--whitelist CIDR,...] [--read-quota N --write-quota N]` | Create a role. |
| `admin role delete CONN_ID --name R --yes` | Delete a role. |

## `udf` — Lua user-defined functions

| Verb | One-liner |
|------|-----------|
| `udf list CONN_ID` | List registered UDF modules (filename, type=LUA, hash). |
| `udf upload CONN_ID --file ./m.lua [--filename m.lua]` | Register a Lua module (basename auto-derived from --file). |
| `udf remove CONN_ID --filename m.lua --yes` | Drop a module. |

## Global flags (apply to every verb)

| Flag | One-liner |
|------|-----------|
| `--config PATH` | Override config file path (default `~/.ackoctl/config.yaml`). |
| `--context NAME` | Override current context. |
| `--server URL` | Override server (cluster-manager base URL). |
| `--token TOKEN` | Override bearer token. |
| `--workspace ID` | Override workspace ACL scope. |
| `-o, --output table\|json\|yaml` | Output format (default table). |
| `-v, --verbose` | Verbose logging to stderr. |
| `--insecure-skip-tls` | Skip TLS verification (dev only). |
