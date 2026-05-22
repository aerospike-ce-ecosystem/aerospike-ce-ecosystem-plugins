---
name: ackoctl
description: "MUST USE when the user drives Aerospike clusters via the ackoctl CLI — connections, records/sets/queries, secondary indexes, operator notes, operational guides, raw asinfo, K8s AerospikeCluster CRs (list/get/scale/logs/events/pods/reconcile), admin users/roles, and Lua UDFs. ALWAYS read the workspace's data-plane / control-plane operational guide with `ackoctl guide get` before running any data or cluster operation, and follow the org/team policy it states. Triggers on: ackoctl, ackoctl guide, manage Aerospike connection, browse records, run query, scale cluster, register UDF, create Aerospike user, read operational guide. Replaces the retired ACM MCP server — canonical way to drive cluster-manager from Claude Code."
---

# ackoctl — cluster-manager CLI for Claude Code

`ackoctl` is the [Go CLI](https://github.com/aerospike-ce-ecosystem/ackoctl) for [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager). It calls cluster-manager's REST API at `/api/v1/*` — it does **not** talk to Kubernetes or Aerospike directly, so every action is mediated by the same FastAPI surface that the web UI uses.

This skill replaces the legacy `acm-mcp-init` skill. The MCP HTTP server inside cluster-manager has been retired in favor of the CLI: there is **no `claude mcp add`**, no DNS-rebinding allowlist, and no Origin allowlist — the security surface shrank because there is no MCP HTTP server. Claude shells out to `ackoctl` like it would to `kubectl` or `gh`.

When in doubt about a specific invocation, consult [`./reference/commands.md`](./reference/commands.md).

## 0. Read the operational guides first — mandatory

Operational guides are workspace-scoped Markdown policy documents that acko
administrators register in cluster-manager. They are the **authoritative
org/team policy** for what may be done with Aerospike data and clusters —
TTL ceilings for throwaway data, required `note` templates, which environments
may be created and how, approval gates, and so on.

**Before running any mutating `ackoctl` command, read the relevant guide and
follow it.** This is not optional — the guides exist so an administrator can
control data and cluster operations dynamically, server-side, without changing
this skill.

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

1. Decide whether the task touches the **data plane** (records / sets /
   indexes / notes) or the **control plane** (connections / clusters / admin).
2. Run `ackoctl guide get <data-plane|control-plane>` for the active workspace
   and read the returned Markdown **in full**.
3. Apply every policy it states. Example data-plane policy: "temporary test
   data must set TTL ≤ 7 days and carry a `note` using the template
   `creator: … / date: …`". Example control-plane policy: "test clusters must
   be created in-memory only; stage uses the `soft-rack` template; prod is not
   created directly — get approval first".
4. Only then run the ackoctl command(s). If the guide forbids or constrains the
   request, surface that to the user before acting.

If `ackoctl guide get …` returns **404** the guide is not registered yet — tell
the user, proceed with standard caution, and do **not** invent a policy.

Guides are authored and edited by administrators in the cluster-manager web UI
under **Operational guides** (`/guides`). See [§4 `guide`](#guide--operational-guides-orgteam-policy)
for the read-only CLI surface.

## 1. Install

```bash
# macOS and Linux — same one-liner, no Homebrew required
curl -fsSL https://raw.githubusercontent.com/aerospike-ce-ecosystem/ackoctl/main/install.sh | sh

# Verify
ackoctl version
```

Wheels for darwin/linux × amd64/arm64 are detected automatically and the sha256 is verified before install. For pinned versions, `BIN_DIR`, manual install or source build, see [ackoctl install docs](https://github.com/aerospike-ce-ecosystem/ackoctl/blob/main/docs/install.md).

## 2. Configure

`ackoctl` reads `~/.ackoctl/config.yaml` — same kubeconfig-style multi-context shape kubectl uses.

```bash
# Register a context pointing at a local cluster-manager
ackoctl config set-context kind-local \
  --server=http://localhost:8000/api \
  --workspace-id=default

# Register a prod context with a bearer token
ackoctl config set-context prod \
  --server=https://acm.example.com/api \
  --token=eyJ... \
  --workspace-id=prod-us

ackoctl config use-context kind-local
ackoctl config current-context
ackoctl config view -o yaml
```

Override priority: **CLI flag > environment variable > config file**.

| Env var | Equivalent flag | Notes |
|---------|-----------------|-------|
| `ACKOCTL_CONFIG`    | `--config`    | Override config file location |
| `ACKOCTL_CONTEXT`   | `--context`   | Pick a context for this call |
| `ACKOCTL_SERVER`    | `--server`    | One-off server override |
| `ACKOCTL_TOKEN`     | `--token`     | Bearer JWT (no interactive login) |
| `ACKOCTL_WORKSPACE` | `--workspace` | Workspace ID for ACL scoping |

`ackoctl` has no `login` command — bring your own OIDC JWT (Keycloak CLI, browser device flow, etc.). Use `--insecure-skip-tls` for dev-only TLS bypass and `-v` for verbose logging to stderr.

## 3. Command grammar

```
ackoctl <noun> <verb> [flags]
```

gh / aws / kubectl style: `ackoctl connection list`, not `ackoctl get connections`.

| Flag | Default | Description |
|------|---------|-------------|
| `-o table\|json\|yaml` | `table` | Output format. Use `-o json`/`-o yaml` for any scripted consumption. |
| `--workspace ID` | from current context | Workspace ACL scope — never falls back to "first workspace" silently. |
| `--context NAME` | `current-context` | Use a specific context for this call. |
| `--server URL` / `--token TOKEN` | from context | One-off overrides. |

For lists and gets, default to `-o table` for human consumption and switch to `-o json` / `-o yaml` whenever Claude needs to parse the output downstream.

## 4. Commands by noun

### guide — operational guides (org/team policy)

Read-only access to the workspace's operational guides. **Run these before any
data or cluster operation** — see [§0](#0-read-the-operational-guides-first--mandatory).

```bash
ackoctl guide list                              # guides registered for the workspace (data-plane and/or control-plane)
ackoctl guide get data-plane                    # prints the Markdown policy body
ackoctl guide get control-plane
ackoctl guide get data-plane --workspace=ws-team-a
ackoctl guide get control-plane -o json         # structured: title, timestamps, author
```

`guide get` prints the raw Markdown to stdout under the default output (easy to
read and pipe); `-o json` / `-o yaml` emit the full structured guide. The
workspace comes from `--workspace` or the current context; **unlike other
resource commands**, `guide` falls back to the built-in `ws-default` workspace
when neither is set (it does not error out) — `ws-default` always exists and is
readable by every authenticated caller. Guides are authored in the
cluster-manager web UI — there is no `guide create/edit` verb in ackoctl.

### connection — Aerospike connection profiles

```bash
ackoctl connection list
ackoctl connection get <ID>
ackoctl connection create \
  --name local-aero \
  --host aerospike-node-1 --host aerospike-node-2 \
  --port 3000 \
  --label env=dev --label team=platform
ackoctl connection health <ID>     # live probe — always returns 200; see `connected` field
```

`update` and `delete` follow the same noun/verb pattern. Connection IDs are stable UUIDs — store them in scripts; names can change.

### cluster — cluster inspection and namespace tuning

```bash
ackoctl cluster info <CONN_ID> -o yaml
ackoctl cluster configure-namespace <CONN_ID> \
  --name=test \
  --param=evict-used-pct=70 \
  --param=stop-writes-sys-memory-pct=90
```

`configure-namespace` issues `asinfo set-config` under the hood — only **runtime-mutable** namespace knobs apply. Aerospike CE cannot create namespaces at runtime: those live in `aerospike.conf` (managed by ACKO).

### set — derived set inventory

```bash
ackoctl set list <CONN_ID>                       # all namespaces
ackoctl set list <CONN_ID> --namespace=test      # one namespace
```

There is no dedicated `/sets` endpoint; ackoctl pulls cluster info and projects `namespaces[].sets[]`.

### record — data plane

```bash
ackoctl record list   <CONN_ID> --namespace=test --set=users --page-size=100
ackoctl record get    <CONN_ID> --namespace=test --set=users --pk=alice
ackoctl record put    <CONN_ID> --namespace=test --set=users --pk=alice \
  --bins='{"name":"Alice","age":30}' --ttl=3600
ackoctl record delete <CONN_ID> --namespace=test --set=users --pk=alice --yes
ackoctl record query  <CONN_ID> --namespace=test --set=users \
  --pk-pattern='ali' --pk-match-mode=prefix --select=name,age --page-size=50
```

`--filter` / `--predicate` accept raw JSON for the full `FilterGroup` / `QueryPredicate` DSL. `--pk-type` pins the particle type (`auto|string|int|bytes`); `auto` retries the alternate type on `NOT_FOUND`.

### query — predicate, pk-lookup, full scan

```bash
# Predicate — --value/--value2 parse as JSON, so 30 stays int and "alice" stays string
ackoctl query exec <CONN_ID> --namespace=test --set=users \
  --bin=age --op=between --value=18 --value2=30 --select=name,age

# Primary-key lookup
ackoctl query exec <CONN_ID> --namespace=test --set=users \
  --primary-key=alice --pk-type=string

# Full scan capped at 1000
ackoctl query exec <CONN_ID> --namespace=test --set=users --max-records=1000
```

Operators: `equals | between | contains | geo_within_region | geo_contains_point`.

### index — secondary indexes

```bash
ackoctl index list   <CONN_ID>
ackoctl index create <CONN_ID> --namespace=test --set=users \
  --bin=age --name=idx_age --type=numeric
ackoctl index delete <CONN_ID> --namespace=test --name=idx_age --yes
```

`--type`: `numeric | string | geo2dsphere`.

### note — operator notes on sets and records

```bash
# Set-level notes
ackoctl note set update <CONN_ID> --namespace=test --set=users \
  --note='migration in progress — ticket OPS-1234'
ackoctl note set list   <CONN_ID>
ackoctl note set delete <CONN_ID> --namespace=test --set=users --yes

# Record-level notes
ackoctl note record update <CONN_ID> --namespace=test --set=users \
  --pk=alice --note='under investigation, do not delete'
ackoctl note record list   <CONN_ID> --namespace=test --set=users
```

Notes live in cluster-manager's metaDB (not in Aerospike). They are scoped per connection profile and cascade-delete with the connection. Use them to attach runbook context, ticket references, or known-issue annotations.

### k8s — ACKO-managed AerospikeCluster CRs

Requires cluster-manager to have `K8S_MANAGEMENT_ENABLED=true`. Otherwise the server returns 404.

```bash
ackoctl k8s cluster list                                 # all AerospikeCluster CRs
ackoctl k8s cluster get aerospike/sample-cluster         # <namespace>/<name>
ackoctl k8s cluster reconcile aerospike/sample-cluster   # stamp acko.io/force-reconcile
ackoctl k8s cluster scale aerospike/sample-cluster --size=5
ackoctl k8s cluster logs aerospike/sample-cluster --pod=sample-cluster-0-0 \
  --container=aerospike-server --since=5m --tail=200
ackoctl k8s cluster events aerospike/sample-cluster --since=30m
```

Cluster identifiers use the `"<namespace>/<name>"` form — always quote them in shell.

### info — raw asinfo via cluster-manager

```bash
# Whitelisted read verbs (status, statistics, namespace/<ns>, ...) — safe by default
ackoctl info <CONN_ID> --command='statistics'
ackoctl info <CONN_ID> --command='namespace/test'
ackoctl info <CONN_ID> --command='status' --node=BB9020014270008

# Multiple verbs in one call: --command is repeatable
ackoctl info <CONN_ID> --command=build --command=version

# Mutation verbs (set-config:, recluster:, ...) require --allow-write
ackoctl info <CONN_ID> --command='set-config:context=service;proto-fd-max=20000' --allow-write
```

`ackoctl info` always reaches cluster-manager; it never bypasses the workspace ACL. For diagnostic reads under restricted profiles, the whitelisted-verbs path is the default; mutation verbs are an explicit opt-in via `--allow-write`.

### admin — users and roles (security-enabled clusters)

```bash
# Users — --username and --roles (comma-separated; repeatable on cli).
# --password-stdin avoids shell-history disclosure of the plaintext password.
ackoctl admin user list   <CONN_ID>
ackoctl admin user create <CONN_ID> --username=alice --password-stdin --roles=read-write,data-admin
ackoctl admin user passwd <CONN_ID> --username=alice --password-stdin
ackoctl admin user delete <CONN_ID> --username=alice --yes

# Roles — --privilege is CODE[:NS[/SET]], repeatable.
ackoctl admin role list   <CONN_ID>
ackoctl admin role create <CONN_ID> --name=ops-readonly --privilege=read --privilege=read:test/users
ackoctl admin role delete <CONN_ID> --name=ops-readonly --yes
```

The target cluster must have security enabled in `aerospike.conf`. CE clusters managed by ACKO do **not** have enterprise security; these commands return HTTP 403 (`Security is not enabled. Add a 'security { }' block to aerospike.conf …`) when ackoctl is pointed at a CE cluster. They only apply when ackoctl is pointed at an Aerospike Enterprise cluster (a supported cluster-manager mode, but out of the CE happy path). The user role mutation path is **create / delete only** — there is no `grant`/`revoke` verb; change a user's roles by deleting and recreating.

### udf — Lua UDF module management

```bash
ackoctl udf list   <CONN_ID>
ackoctl udf upload <CONN_ID> --file=./examples/sum.lua
ackoctl udf remove <CONN_ID> --filename=sum.lua --yes
```

UDF registration is cluster-wide; the operator note (`ackoctl note record update`) is the right place to record provenance / ticket links for the module.

## 5. Workspace ACL and auth

- `--workspace ID` is honored on every resource command. The default comes from the active context's `workspace-id`. ackoctl never falls back to "first workspace" silently — missing scope is a hard error.
- Auth is **bearer token only**. There is no `ackoctl login`; users bring their own OIDC JWT (Keycloak CLI, browser device flow, …) and store it in the context or pass it per-call via `--token` / `ACKOCTL_TOKEN`.
- For multi-cluster ACKO, register one context per cluster-manager instance (`kind-local`, `prod-us`, `prod-eu`) and switch with `ackoctl config use-context <name>` or per-call `--context`.

## 6. Links

- **ackoctl repo** — https://github.com/aerospike-ce-ecosystem/ackoctl
- **ackoctl usage cheat sheet** — https://github.com/aerospike-ce-ecosystem/ackoctl/blob/main/docs/usage.md
- **cluster-manager** — https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager
- **cluster-manager REST docs** — `GET /api/openapi.json` on a running instance, or the cluster-manager repo's `docs/api/`.
- **command reference** — [`./reference/commands.md`](./reference/commands.md)
