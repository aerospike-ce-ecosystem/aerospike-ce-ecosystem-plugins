# aerospike-ce-ecosystem

Claude Code plugin for the Aerospike CE ecosystem — deploy clusters on Kubernetes with [ACKO](https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator) and build Python applications with [aerospike-py](https://github.com/aerospike-ce-ecosystem/aerospike-py).

## Installation

### From GitHub (recommended)

Add the repository as a marketplace, then install:

```bash
# Step 1: Add as marketplace
claude plugin marketplace add aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins

# Step 2: Install the plugin
claude plugin install aerospike-ce-ecosystem
```

### Project-scoped install

To install only for the current project:

```bash
claude plugin marketplace add aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins
claude plugin install aerospike-ce-ecosystem -s project
```

### Verify installation

```bash
claude plugin list
# Should show: aerospike-ce-ecosystem@aerospike-ce-ecosystem ✔ enabled
```

## Skills

### ACKO (Aerospike CE Kubernetes Operator)

| Skill | Trigger | Description |
|-------|---------|-------------|
| **acko-deploy** | "deploy Aerospike on Kubernetes" | Step-by-step guide to deploy CE clusters via AerospikeCluster CR — 8 scenarios from minimal to full-featured |
| **acko-operations** | "scale Aerospike cluster" | Day-2 operations: scale, upgrade, dynamic config, warm restart, ACL, pause/resume, troubleshooting |
| **acko-config-reference** | *(background)* | CE 8.1 parameter reference, CRD-to-conf mapping, webhook validation rules |

### aerospike-py (Python Client)

| Skill | Trigger | Description |
|-------|---------|-------------|
| **aerospike-py-api** | "use aerospike-py to ..." | Full API reference — AsyncClient, CRUD, batch, CDT, query, expressions, observe, admin |
| **aerospike-py-fastapi** | "build FastAPI app with Aerospike" | Production-ready FastAPI patterns — lifespan, DI, CRUD endpoints, error handling, metrics |

### Cluster Manager CLI (ackoctl)

| Skill | Trigger | Description |
|-------|---------|-------------|
| **ackoctl** | "ackoctl", "manage Aerospike connection", "browse records", "register UDF", "scale cluster" | Drive [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager) via the [ackoctl](https://github.com/aerospike-ce-ecosystem/ackoctl) CLI — connections, cluster info, records/sets, queries, secondary indexes, operator notes, raw asinfo, K8s AerospikeCluster CRs, admin (users/roles), and Lua UDF modules. Multi-cluster ACKO friendly via kubeconfig-style contexts. |
| **acko-debugging** | "CrashLoopBackOff", "phase=Error", "reconcile failure", "migration stuck" | Systematic 6-step diagnosis procedure for ACKO clusters with CE 8.1 pitfalls and a remediation matrix. Routes both data-plane and K8s-plane probes through ackoctl (`ackoctl cluster info`, `ackoctl info exec`, `ackoctl query exec`, `ackoctl k8s cluster get/list`, `ackoctl k8s pod logs`, `ackoctl k8s events list`); falls back to `kubectl`/`asinfo` when ackoctl is unavailable. |

## ackoctl integration

Live cluster access goes through the [ackoctl](https://github.com/aerospike-ce-ecosystem/ackoctl) Go CLI, which calls [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager)'s REST API at `/api/v1/*`. There is no MCP HTTP server in the loop, so there is no DNS-rebinding allowlist, no Origin allowlist, and no per-cluster `claude mcp add` step — the security surface is just the existing cluster-manager FastAPI auth (bearer JWT + workspace ACL).

```bash
# 1. Install ackoctl
curl -fsSL https://raw.githubusercontent.com/aerospike-ce-ecosystem/ackoctl/main/install.sh | sh

# 2. Point a context at a running cluster-manager
ackoctl config set-context kind-local \
  --server=http://localhost:8000/api \
  --workspace-id=default
ackoctl config use-context kind-local

# 3. Use the cluster from any agent / chat
#    "in kind-local, list connections and get a sample record from sample_set"
ackoctl connection list
ackoctl record list <CONN_ID> --namespace=test --set=sample_set --page-size=5
```

For multi-cluster ACKO, register one context per cluster-manager instance — naming convention `<env>` or `<region>`:

```bash
ackoctl config set-context prod-us \
  --server=https://acm.prod-us.example.com/api \
  --token=$ACKOCTL_TOKEN \
  --workspace-id=prod-us
ackoctl --context=prod-us k8s cluster list
```

Auth is bearer-token only — users bring their own OIDC JWT (Keycloak CLI, browser device flow, …). The workspace ACL on cluster-manager scopes every call; destructive verbs (`delete`, `remove`, mutation `info exec --allow-write`, `k8s cluster scale`) require `--yes` for non-interactive runs.

The `ackoctl` skill covers install, configuration, and every command (connection / cluster / set / record / query / index / note / k8s / info / admin / udf). See `skills/ackoctl/reference/commands.md` for a one-line-per-command cheat sheet.

## Prerequisites

### For ACKO skills

- Kubernetes cluster (kind, minikube, EKS, GKE, etc.)
- [ACKO operator](https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator) installed
- `kubectl` configured

### For aerospike-py skills

- Python 3.9+
- Running Aerospike server (localhost:3000 by default)

## Benchmark Results

Evaluated with Claude Sonnet on real deployment tasks:

| Metric | with skill | without skill | Improvement |
|--------|-----------|---------------|-------------|
| **Pass Rate** | 100% | 87.5% | +12.5% |
| **Token Usage** | 25,077 | 36,262 | -30.8% |
| **Completion Time** | 73.8s | 137.4s | -46.3% |
| **Tool Calls** | 8.0 | 30.0 | -73.3% |

Key findings:
- Skills prevent the #1 CE mistake (enterprise-only config in CE clusters)
- aerospike-py-specific patterns (NamedTuple access, Depends injection) are taught by skills
- 7 production bonus features generated with skill vs 0 without

## Development

### Validate the plugin

```bash
claude plugin validate /path/to/aerospike-ce-ecosystem-plugins
```

### Run eval tests

```bash
# With skill
claude -p "Deploy a single-node Aerospike cluster for development on a kind cluster" --model sonnet

# Without skill (baseline comparison)
claude -p "Deploy a single-node Aerospike cluster for development on a kind cluster" --model sonnet --disable-plugins
```

> The `e2e_pytest/` scenario suite includes a **multi-cluster + Keycloak OIDC** scenario (common-cluster web + dev/prod operator-cluster API + bitnami/keycloak realm bootstrap). See [ACKO multi-cluster docs](https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator/blob/main/docs/multi-cluster-keycloak.md).

## License

MIT
