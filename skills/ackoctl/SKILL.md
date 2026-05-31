---
name: ackoctl
description: "MUST USE when the user drives Aerospike clusters via the ackoctl CLI — connections, records/sets/queries, secondary indexes, operator notes, operational guides, raw asinfo, K8s AerospikeCluster CRs (list/get/scale/logs/events/pods/reconcile), admin users/roles, and Lua UDFs. ALWAYS read the workspace's data-plane / control-plane operational guide with `ackoctl guide get` before running any data or cluster operation, and follow the org/team policy it states. Triggers on: ackoctl, ackoctl guide, manage Aerospike connection, browse records, run query, ackoctl k8s cluster scale, register UDF, create Aerospike user, read operational guide. Replaces the retired ACM MCP server — canonical way to drive cluster-manager from Claude Code."
---

# ackoctl — cluster-manager CLI for Claude Code

`ackoctl` is the Go CLI for [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager). It calls cluster-manager's REST API at `/api/v1/*` — it does **not** talk to Kubernetes or Aerospike directly, so every action is mediated by the same FastAPI surface the web UI uses, including the workspace ACL.

It replaces the legacy `acm-mcp-init` skill: the MCP HTTP server has been retired, so there is no `claude mcp add`, no DNS-rebinding/Origin allowlist. Claude shells out to `ackoctl` like `kubectl` or `gh`.

When in doubt about a specific invocation, consult [`./reference/commands.md`](./reference/commands.md).

## 0. Read the operational guides first — mandatory

Operational guides are workspace-scoped Markdown policy documents that acko administrators register in cluster-manager. They are the **authoritative org/team policy** for what may be done with Aerospike data and clusters — TTL ceilings, required `note` templates, which environments may be created, approval gates, and so on.

**Before running any mutating `ackoctl` command, read the relevant guide and follow it.**

| Before you run … | First read |
|---|---|
| `record put/delete`, `set truncate`, `index create/delete`, `note …`, `cluster configure-namespace`, mutating `query` | `ackoctl guide get data-plane` |
| `connection create/update/delete`, `k8s cluster create/scale/delete/reconcile`, `info … --allow-write`, `admin user/role …` | `ackoctl guide get control-plane` |

```bash
ackoctl guide list                # which guides the workspace has registered
ackoctl guide get data-plane      # policy for Aerospike data CRUD
ackoctl guide get control-plane   # policy for Aerospike cluster lifecycle
```

Workflow every time:

1. Decide whether the task touches the **data plane** (records / sets / indexes / notes) or the **control plane** (connections / clusters / admin).
2. Run `ackoctl guide get <data-plane|control-plane>` for the active workspace and read the returned Markdown **in full**.
3. Apply every policy it states (e.g. data-plane: "temporary test data must set TTL ≤ 7 days and carry a `note`"; control-plane: "test clusters in-memory only; prod requires approval").
4. Only then run the command(s). If the guide forbids or constrains the request, surface that to the user before acting.

If `ackoctl guide get …` returns **404** the guide is not registered yet — tell the user, proceed with standard caution, and do **not** invent a policy.

Guides are authored by administrators in the cluster-manager web UI under **Operational guides** (`/guides`). There is no `guide create/edit` verb in ackoctl. See [§4 `guide`](#guide--operational-guides-orgteam-policy).

## 1. Install

```bash
curl -fsSL https://raw.githubusercontent.com/aerospike-ce-ecosystem/ackoctl/main/install.sh | sh
ackoctl version
```

Wheels for darwin/linux × amd64/arm64 are auto-detected and sha256-verified. For pinned versions, `BIN_DIR`, manual install or source build, see [install docs](https://github.com/aerospike-ce-ecosystem/ackoctl/blob/main/docs/install.md).

## 2. Configure

`ackoctl` reads `~/.ackoctl/config.yaml` (kubeconfig-style multi-context).

```bash
ackoctl config set-context kind-local \
  --server=http://localhost:8000/api \
  --workspace-id=default

ackoctl config set-context prod \
  --server=https://acm.example.com/api --token=eyJ... --workspace-id=prod-us

ackoctl config use-context kind-local
ackoctl config current-context
ackoctl config view -o yaml
```

`--server` is validated at `set-context` time and must be a well-formed `http(s)` URL with a host, else the command errors before saving.

| Env var | Equivalent flag | Notes |
|---------|-----------------|-------|
| `ACKOCTL_CONTEXT`           | `--context`           | Pick a context for this call |
| `ACKOCTL_SERVER`            | `--server`            | One-off server override |
| `ACKOCTL_TOKEN`             | `--token`             | Bearer JWT (no interactive login) |
| `ACKOCTL_WORKSPACE`         | `--workspace`         | Workspace ID for ACL scoping |
| `ACKOCTL_INSECURE_SKIP_TLS` | `--insecure-skip-tls` | Bool; skip TLS verification (dev only) |

Priority: **flag > env > config file**. `ackoctl` has no `login` command — bring your own OIDC JWT. The config-file path comes only from `--config` (there is no `ACKOCTL_CONFIG` env var). `-v` enables verbose logging to stderr.

## 3. Command grammar

```
ackoctl <noun> <verb> [flags]
```

gh / aws / kubectl style: `ackoctl connection list`, not `ackoctl get connections`.

Global flags: `-o table|json|yaml` (default `table`; use json/yaml for scripted parsing), `--workspace ID` (ACL scope, never silently falls back to "first workspace"), `--context NAME`, `--server URL`, `--token TOKEN`, `--insecure-skip-tls`, `-v`.

### Exit codes

`ackoctl` returns structured codes so scripts/CI can branch on the failure class:

| Code | Meaning |
|------|---------|
| `0` | success |
| `1` | generic / config error (e.g. no current context) |
| `4` | cluster-manager **4xx** — bad request, auth, not-found; retry won't help |
| `5` | cluster-manager **5xx** — server / transient; retry may help |
| `130` | aborted by signal (ctrl-c / SIGTERM) |

## 4. Commands by noun

### guide — operational guides (org/team policy)

Read-only. **Run before any data or cluster operation** — see [§0](#0-read-the-operational-guides-first--mandatory).

```bash
ackoctl guide list
ackoctl guide get data-plane                    # prints the Markdown policy body to stdout
ackoctl guide get control-plane --workspace=ws-team-a
ackoctl guide get data-plane -o json            # structured: title, timestamps, author
```

`GUIDE_TYPE` must be `data-plane` or `control-plane`. Default output prints raw Markdown; `-o json|yaml` emits the structured guide. **Unlike other resource commands**, `guide` falls back to the built-in `ws-default` workspace when neither `--workspace` nor the context supplies one (it does not error), announcing the fallback on stderr.

### connection — Aerospike connection profiles

```bash
ackoctl connection list
ackoctl connection get <ID>
ackoctl connection create \
  --name local-aero --host node-1 --host node-2 --port 3000 \
  --label env=dev --label team=platform
ackoctl connection health <ID>     # live probe — see the `connected` field
```

- `--host` is repeatable; `--port` must be 1..65535.
- `--color` (UI accent) must be a `#RRGGBB` hex triplet, validated client-side.
- Duplicate `--label` keys are rejected (`--label env=a --label env=b` errors).
- `--password` and `--password-stdin` are **mutually exclusive** (parse-time error); prefer `--password-stdin`. Password is optional on create/update.

`update`/`delete` follow the same pattern. IDs are stable UUIDs — store them in scripts; names can change. `delete` needs `--yes`.

### cluster — inspection and namespace tuning

```bash
ackoctl cluster info <CONN_ID> -o yaml
ackoctl cluster configure-namespace <CONN_ID> --name=test \
  --param=evict-used-pct=70 --param=stop-writes-sys-memory-pct=90
```

`configure-namespace` issues `asinfo set-config` — only **runtime-mutable** knobs apply; CE cannot create namespaces at runtime (they live in `aerospike.conf`, managed by ACKO). At least one `--param` is required; duplicate `--param` keys are rejected; `--param name=…` is reserved (use `--name`).

### set — set inventory + truncate

```bash
ackoctl set list <CONN_ID> [--namespace=test]
ackoctl set truncate <CONN_ID> --namespace=test --set=users [--before-lut N] --yes
```

`list` is derived from cluster info (no dedicated `/sets` endpoint). `truncate` is destructive (`--yes` required); `--before-lut` (optional ns cutoff) must be a **positive** timestamp — omit it for a full wipe.

### record — data plane

```bash
ackoctl record list   <CONN_ID> --namespace=test --set=users --page-size=100
ackoctl record get    <CONN_ID> --namespace=test --set=users --pk=alice
ackoctl record put    <CONN_ID> --namespace=test --set=users --pk=alice \
  --bins='{"name":"Alice","age":30}' --ttl=3600
ackoctl record delete     <CONN_ID> --namespace=test --set=users --pk=alice --yes
ackoctl record delete-bin <CONN_ID> --namespace=test --set=users --pk=alice --bin=age --yes
ackoctl record query  <CONN_ID> --namespace=test --set=users \
  --pk-pattern='ali' --pk-match-mode=prefix --select=name,age --page-size=50
```

- `--bins` must be a **non-empty JSON object**.
- `--ttl`: `-1` (never expire), `0` (namespace default), or a positive number of seconds.
- `--pk-type` pins the particle type (`auto|string|int|bytes`); `auto` retries the alternate type on `NOT_FOUND`.
- `--page-size` is 1..500; `record query --page` ≥ 1.
- `record query` `--filter` / `--predicate` must each be a **non-empty JSON object** (arrays, scalars, and `null` are rejected client-side).

### query — predicate, pk-lookup, full scan

```bash
ackoctl query exec <CONN_ID> --namespace=test --set=users \
  --bin=age --op=between --value=18 --value2=30 --select=name,age
ackoctl query exec <CONN_ID> --namespace=test --set=users --primary-key=alice --pk-type=string
ackoctl query exec <CONN_ID> --namespace=test --set=users --max-records=1000
```

Operators: `equals | between | contains | geo_within_region | geo_contains_point`. `--value2` is only valid with `between`. `--max-records` is `0` (server default) or 1..1000000.

`--value`/`--value2`: barewords are kept as strings, so `--value alice` works unquoted and numeric-looking-but-non-JSON values (`007`, `1.2.3`, `+5`) stay strings; only `{`/`[`/`"`-prefixed input must be valid JSON (else it errors rather than silently becoming a string).

### index — secondary indexes

```bash
ackoctl index list   <CONN_ID>
ackoctl index create <CONN_ID> --namespace=test --set=users --bin=age --name=idx_age --type=numeric
ackoctl index delete <CONN_ID> --namespace=test --name=idx_age --yes
```

`create` requires `--namespace --set --bin --name --type`; `--type` is `numeric|string|geo2dsphere`.

### note — operator notes on sets and records

```bash
ackoctl note set    update <CONN_ID> --namespace=test --set=users --note='migration — OPS-1234'
ackoctl note set    list   <CONN_ID> [--namespace=test]
ackoctl note set    delete <CONN_ID> --namespace=test --set=users --yes
ackoctl note record update <CONN_ID> --namespace=test --set=users --pk=alice --note='do not delete'
ackoctl note record list   <CONN_ID> --namespace=test --set=users
ackoctl note record delete <CONN_ID> --namespace=test --set=users --pk=alice --yes
```

`--note` must be non-empty (whitespace-only is rejected), up to 8 KB. Notes live in cluster-manager's metaDB (not Aerospike), are scoped per connection, and cascade-delete with it.

### k8s — ACKO-managed AerospikeCluster CRs

Requires cluster-manager `K8S_MANAGEMENT_ENABLED=true`, else every k8s subcommand returns 404.

```bash
ackoctl k8s cluster list
ackoctl k8s cluster get aerospike/sample-cluster         # NAMESPACE/NAME
ackoctl k8s cluster reconcile aerospike/sample-cluster   # stamp acko.io/force-reconcile
ackoctl k8s cluster scale aerospike/sample-cluster --size=5
ackoctl k8s cluster pods   aerospike/sample-cluster
ackoctl k8s cluster logs   aerospike/sample-cluster --pod=sample-cluster-0-0 \
  --container=aerospike-server --since=5m --tail=200
ackoctl k8s cluster events aerospike/sample-cluster --since=30m
```

- Cluster identifiers use `NAMESPACE/NAME` — quote them in shell. An extra path segment (`ns/name/extra`) is rejected.
- `scale --size` must be **1..8** (CE node cap); scale-down (target < current) requires `-y/--yes`. If the current size can't be read, ackoctl fails closed and demands `--yes`.
- `--since` on `logs`/`events` is client-side; `--tail` is 1..10000.

### info — raw asinfo via cluster-manager

```bash
ackoctl info <CONN_ID> --command='statistics'
ackoctl info <CONN_ID> --command=build --command=version            # --command repeatable
ackoctl info <CONN_ID> --command='status' --node=BB9020014270008
ackoctl info <CONN_ID> --command='set-config:context=service;proto-fd-max=20000' --allow-write
```

Read verbs run against the cluster-manager read-only whitelist by default. Mutation verbs (`set-config:`, `recluster:`, …) require `--allow-write`. `--command` must be non-empty; omit `--node` to fan out across nodes. Always mediated by the workspace ACL.

### admin — users and roles (security-enabled clusters)

```bash
ackoctl admin user list   <CONN_ID>
ackoctl admin user create <CONN_ID> --username=alice --password-stdin --roles=read-write,data-admin
ackoctl admin user passwd <CONN_ID> --username=alice --password-stdin
ackoctl admin user delete <CONN_ID> --username=alice --yes

ackoctl admin role list   <CONN_ID>
ackoctl admin role create <CONN_ID> --name=ops-ro --privilege=read --privilege=read:test/users
ackoctl admin role delete <CONN_ID> --name=ops-ro --yes
```

- `--password`/`--password-stdin` are mutually exclusive and exactly one is required for create/passwd.
- `--roles` and `--whitelist` strip blank entries (a trailing comma is tolerated).
- `--privilege` is `CODE[:NS[/SET]]`; an embedded extra `/` or `:` in the NS/SET segment is rejected.
- `--read-quota`/`--write-quota`, when set, must be positive.

The target cluster must have security enabled in `aerospike.conf`. **CE clusters have no enterprise security**, so these calls fail server-side (`Security is not enabled…`) — a 5xx that maps to **exit code 5**. They are only useful against an Aerospike Enterprise cluster. The role-mutation path is **create / delete only** — no `grant`/`revoke`; change a user's roles by delete + recreate.

### udf — Lua UDF module management

```bash
ackoctl udf list   <CONN_ID>
ackoctl udf upload <CONN_ID> --file=./examples/sum.lua [--filename=sum.lua]
ackoctl udf remove <CONN_ID> --filename=sum.lua --yes
```

`--filename` defaults to the basename of `--file`; cluster-manager validates it against `^[a-zA-Z0-9_.-]{1,255}$`. UDF registration is cluster-wide.

## 5. Workspace ACL and auth

- `--workspace ID` is honored on every resource command (default from the context's `workspace-id`); missing scope is a hard error, never a silent "first workspace" (except `guide`, which falls back to `ws-default`).
- Auth is **bearer token only** — no `ackoctl login`. Store the JWT in the context or pass `--token` / `ACKOCTL_TOKEN`.
- For multi-cluster ACKO, register one context per cluster-manager instance and switch with `ackoctl config use-context` or per-call `--context`.

## 6. Links

- **ackoctl repo** — https://github.com/aerospike-ce-ecosystem/ackoctl
- **usage cheat sheet** — https://github.com/aerospike-ce-ecosystem/ackoctl/blob/main/docs/usage.md
- **cluster-manager** — https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager
- **command reference** — [`./reference/commands.md`](./reference/commands.md)
