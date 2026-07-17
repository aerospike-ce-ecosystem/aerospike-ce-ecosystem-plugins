---
name: ackoctl
description: "MUST USE when the user drives Aerospike clusters via the ackoctl CLI — connections, records/sets/queries, secondary indexes, operator notes, operational guides, raw asinfo, K8s AerospikeCluster CRs (list/get/scale/logs/events/pods/reconcile), admin users/roles, and Lua UDFs. ALWAYS read the workspace's data-plane / control-plane operational guide with `ackoctl guide get` before running any data or cluster operation, and follow the org/team policy it states. Triggers on: ackoctl, ackoctl guide, manage Aerospike connection, browse records, run query, ackoctl k8s cluster scale, register UDF, create Aerospike user, read operational guide. Replaces the retired ACM MCP server — canonical way to drive cluster-manager from Claude Code."
---

# ackoctl — cluster-manager CLI for Claude Code

`ackoctl` is the Go CLI for [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager). It calls cluster-manager's REST API at `/api/v1/*` — it does **not** talk to Kubernetes or Aerospike directly, so every action is mediated by the same FastAPI surface the web UI uses, including the workspace ACL. It replaces the retired ACM MCP server — Claude shells out to `ackoctl` like `kubectl` or `gh`. Full per-verb flag reference: [`./reference/commands.md`](./reference/commands.md).

## 0. Read the operational guides first — mandatory

Operational guides are workspace-scoped Markdown policy documents registered by acko administrators in the cluster-manager web UI (**Operational guides** `/guides`; no `guide create/edit` verb in ackoctl). They are the **authoritative org/team policy** — TTL ceilings, required `note` templates, which environments may be created, approval gates. **Before running any mutating `ackoctl` command, read the relevant guide and follow it:**

| Before you run … | First read |
|---|---|
| `record put/delete`, `set truncate`, `index create/delete`, `note …`, `cluster configure-namespace`, mutating `query` | `ackoctl guide get data-plane` |
| `connection create/update/delete`, `k8s cluster create/scale/delete/reconcile`, `info … --allow-write`, `admin user/role …` | `ackoctl guide get control-plane` |

Every time: decide data plane vs control plane → `ackoctl guide get <type>` for the active workspace and read the returned Markdown **in full** → apply every policy it states (e.g. "test data must set TTL ≤ 7 days and carry a `note`"; "prod requires approval") — if the guide forbids or constrains the request, surface that to the user before acting → only then run the command(s).

If `guide get` returns **404** the guide is not registered — tell the user, proceed with standard caution, and do **not** invent a policy. Unlike other resource commands, `guide` falls back to the built-in `ws-default` workspace when none is set (announced on stderr).

## 1. Install

```bash
curl -fsSL https://raw.githubusercontent.com/aerospike-ce-ecosystem/ackoctl/main/install.sh | sh
ackoctl version
```

Binaries for darwin/linux × amd64/arm64, sha256-verified. Pinned versions / `BIN_DIR` / source build: [install docs](https://github.com/aerospike-ce-ecosystem/ackoctl/blob/main/docs/install.md).

## 2. Configure

`ackoctl` reads `~/.ackoctl/config.yaml` (kubeconfig-style multi-context).

```bash
ackoctl config set-context kind-local --server=http://localhost:8000/api --workspace-id=default
ackoctl config set-context prod --server=https://acm.example.com/api --token=eyJ... --workspace-id=prod-us
ackoctl config use-context kind-local
ackoctl config view -o yaml
```

`--server` is validated at `set-context` time (well-formed `http(s)` URL with a host). Env vars mirror the global flags: `ACKOCTL_CONTEXT`, `ACKOCTL_SERVER`, `ACKOCTL_TOKEN`, `ACKOCTL_WORKSPACE`, `ACKOCTL_INSECURE_SKIP_TLS`. Priority: **flag > env > config file**. No `login` command — bring your own OIDC JWT. Config-file path only via `--config` (no `ACKOCTL_CONFIG` env var). `-v` = verbose stderr logging.

## 3. Command grammar

```
ackoctl <noun> <verb> [flags]        # gh / kubectl style: ackoctl connection list
```

Global flags: `-o table|json|yaml` (default `table`; json/yaml for scripted parsing), `--workspace ID` (ACL scope, never silently falls back to "first workspace"), `--context`, `--server`, `--token`, `--insecure-skip-tls`, `-v`.

Exit codes for scripts/CI: `0` success · `1` generic/config error · `4` cluster-manager 4xx (retry won't help) · `5` 5xx (transient; retry may help) · `130` signal.

## 4. Nouns at a glance

Exact flags/constraints per verb: [`./reference/commands.md`](./reference/commands.md).

| Noun | What it does | Anchor example (`C` = CONN_ID) |
|------|--------------|--------------------------------|
| `guide` | Read org/team policy (read-only; see §0) | `ackoctl guide get data-plane` |
| `connection` | Connection profiles (CRUD + `health` probe) | `ackoctl connection create --name local --host node-1 --port 3000` |
| `cluster` | Inspection + runtime namespace tuning | `ackoctl cluster info C -o yaml` |
| `set` | Set inventory + truncate (destructive) | `ackoctl set truncate C --namespace=test --set=users --yes` |
| `record` | Data-plane CRUD + PK-pattern query | `ackoctl record get C --namespace=test --set=users --pk=alice` |
| `query` | Predicate / PK lookup / full scan | `ackoctl query exec C --namespace=test --set=users --bin=age --op=between --value=18 --value2=30` |
| `index` | Secondary indexes (`numeric\|string\|geo2dsphere`) | `ackoctl index create C --namespace=test --set=users --bin=age --name=idx_age --type=numeric` |
| `note` | Notes on sets/records (metaDB, per-connection) | `ackoctl note set update C --namespace=test --set=users --note='OPS-1234'` |
| `k8s cluster` | ACKO CRs — list/get/reconcile/scale/pods/logs/events | `ackoctl k8s cluster scale aerospike/sample-cluster --size=5` |
| `info` | Raw asinfo (read whitelist; mutations need `--allow-write`) | `ackoctl info C --command='statistics'` |
| `admin` | EE users/roles (CE has no security → server-side failure, exit 5) | `ackoctl admin user create C --username=alice --password-stdin --roles=read-write` |
| `udf` | Lua UDF modules (cluster-wide) | `ackoctl udf upload C --file=./sum.lua` |

Notes that trip people up:

- `k8s cluster` needs cluster-manager `K8S_MANAGEMENT_ENABLED=true` (else every subcommand 404s). Identifiers are `NAMESPACE/NAME` — quote them. `scale --size` is 1..8 (CE cap); scale-down needs `-y`, and ackoctl fails closed when the current size can't be read.
- Destructive verbs (`delete`, `truncate`, `udf remove`, …) require `--yes`.
- `record query` / `query exec` JSON flags (`--filter`, `--predicate`) must be non-empty JSON objects; barewords for `--value` stay strings.

## 5. Workspace ACL and auth

- `--workspace ID` is honored on every resource command (default from the context's `workspace-id`); missing scope is a hard error (except `guide` → `ws-default` fallback).
- Auth is **bearer token only**. Store the JWT in the context or pass `--token` / `ACKOCTL_TOKEN`.
- Multi-cluster ACKO: one context per cluster-manager instance; switch via `use-context` or per-call `--context`.

## 6. Links

- **ackoctl repo** — https://github.com/aerospike-ce-ecosystem/ackoctl
- **usage cheat sheet** — https://github.com/aerospike-ce-ecosystem/ackoctl/blob/main/docs/usage.md
- **cluster-manager** — https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager
- **command reference** — [`./reference/commands.md`](./reference/commands.md)
