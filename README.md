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

### Cluster Manager MCP

| Skill | Trigger | Description |
|-------|---------|-------------|
| **acm-mcp-init** | "register ACM MCP", "/acm-mcp-init" | Register one or many [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager) MCP endpoints with Claude Code so other skills/agents can read and operate live clusters. Multi-cluster ACKO friendly. |

### Agents

| Agent | Description |
|-------|-------------|
| **acko-cluster-debugger** | Systematic cluster debugging. Uses ACM MCP tools (`mcp__aerospike-{prefix}__list_namespaces`, `__execute_info`, `__query`, `__get_record`) for data-plane diagnosis; falls back to `kubectl`/`asinfo` for K8s-plane (pods, events, logs). Phase 2 will replace the K8s side with MCP tools too. |

## MCP integration

This plugin uses the [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager) MCP server (21 Voyager-parity tools at `/mcp`) for live cluster access. Endpoints are registered per cluster-manager instance — register one entry per ACKO Helm release if you operate multiple clusters.

```bash
# 1. Start ACM somewhere reachable
ACM_MCP_ENABLED=true uv run uvicorn aerospike_cluster_manager_api.main:app --reload

# 2. Register the endpoint with Claude Code (or invoke the acm-mcp-init skill)
claude mcp add --transport http aerospike-dev http://localhost:8000/mcp

# 3. Use the cluster from any agent / chat
#    "in dev cluster, list namespaces and get a sample record from sample_set"
```

For multi-cluster ACKO, register each cluster-manager separately:

```bash
claude mcp add --transport http aerospike-prod-us \
  https://acm.prod-us.example.com/mcp \
  -H "Authorization: Bearer $ACM_MCP_TOKEN"
```

Tools are addressable as `mcp__aerospike-<name>__<tool>` (e.g. `mcp__aerospike-prod-us__get_record`). Agents pick the right prefix from the user's wording ("in prod-us, …" → `aerospike-prod-us`).

The default ACM access profile is `read_only` — mutation tools (`create_record`, `delete_*`, `truncate_set`, `execute_info` with config-set) are blocked at call time. Set `ACM_MCP_ACCESS_PROFILE=full` on the server to allow mutations.

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
