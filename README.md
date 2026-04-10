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

### Agents

| Agent | Description |
|-------|-------------|
| **acko-cluster-debugger** | Systematic K8s cluster debugging — pod status, events, logs, config analysis |

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

## License

MIT
