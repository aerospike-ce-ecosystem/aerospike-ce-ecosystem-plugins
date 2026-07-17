# aerospike-ce-ecosystem

This Claude Code plugin helps you work with the Aerospike CE ecosystem. Use it to deploy clusters on Kubernetes with [ACKO](https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator) and build Python applications with [aerospike-py](https://github.com/aerospike-ce-ecosystem/aerospike-py).

## Installation

### From GitHub (recommended)

Register this repository as a marketplace, then install the plugin:

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
| **acko-deploy** | "deploy Aerospike on Kubernetes" | Guides you through nine CE deployment scenarios, from a minimal cluster to a full-featured `AerospikeCluster` CR |
| **acko-operations** | "scale Aerospike cluster" | Covers Day-2 operations such as scaling, upgrades, dynamic configuration, warm restarts, ACL, pause/resume, and troubleshooting |
| **acko-config-reference** | *(background)* | Provides the CE 8.1 parameter reference, CRD-to-conf mapping, and webhook validation rules |
| **acko-e2e-test** | "ACKO e2e test", "kind cluster test" | Provides an end-to-end test playbook with canonical scenarios, Ginkgo labels, the required `helm install` operator setup, and release-verification performance checks |

### aerospike-py (Python Client)

| Skill | Trigger | Description |
|-------|---------|-------------|
| **aerospike-py-api** | "use aerospike-py to ..." | Documents the full API, including AsyncClient, CRUD, batch, CDT, query, expressions, observe, and admin operations |
| **aerospike-py-fastapi** | "build FastAPI app with Aerospike" | Shows production FastAPI patterns for lifespan, DI, CRUD endpoints, error handling, and metrics |

### Cluster Manager CLI (ackoctl)

| Skill | Trigger | Description |
|-------|---------|-------------|
| **ackoctl** | "ackoctl", "manage Aerospike connection", "browse records", "register UDF", "scale cluster" | Uses [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager) through the [ackoctl](https://github.com/aerospike-ce-ecosystem/ackoctl) CLI to manage connections, cluster info, records and sets, queries, secondary indexes, operator notes, raw asinfo, K8s `AerospikeCluster` CRs, users and roles, and Lua UDF modules. Kubeconfig-style contexts support multi-cluster ACKO environments. |
| **acko-debugging** | "CrashLoopBackOff", "phase=Error", "reconcile failure", "migration stuck" | Provides a systematic six-step diagnostic procedure for ACKO clusters, including CE 8.1 pitfalls and a remediation matrix. It runs data-plane and K8s-plane probes through ackoctl (`ackoctl cluster info`, `ackoctl info`, `ackoctl query exec`, `ackoctl k8s cluster get/list`, `ackoctl k8s cluster logs`, `ackoctl k8s cluster events`) and falls back to `kubectl` or `asinfo` when ackoctl is unavailable. |

### Ecosystem support

| Skill | Trigger | Description |
|-------|---------|-------------|
| **bug-reporter** | "버그 제보", "where do I file this issue", "report this to GitHub" | Identifies the correct `aerospike-ce-ecosystem` repository from the reported symptoms and prepares a GitHub issue with the required reproduction details |

## ackoctl integration

The plugin accesses live clusters through the [ackoctl](https://github.com/aerospike-ce-ecosystem/ackoctl) Go CLI. The CLI calls the [aerospike-cluster-manager](https://github.com/aerospike-ce-ecosystem/aerospike-cluster-manager) REST API at `/api/v1/*`.

This path does not use an MCP HTTP server. You therefore do not need a DNS-rebinding allowlist, an Origin allowlist, or a separate `claude mcp add` step for each cluster. Authentication remains within the existing cluster-manager FastAPI security model: bearer JWT plus workspace ACL.

```bash
# 1. Install ackoctl
curl -fsSL https://raw.githubusercontent.com/aerospike-ce-ecosystem/ackoctl/main/install.sh | sh

# 2. Point a context at a running cluster-manager
ackoctl config set-context kind-local \
  --server=http://localhost:8000/api \
  --workspace-id=default
ackoctl config use-context kind-local

# 3. Use the cluster from any skill or chat
#    "in kind-local, list connections and get a sample record from sample_set"
ackoctl connection list
ackoctl record list <CONN_ID> --namespace=test --set=sample_set --page-size=5
```

For a multi-cluster ACKO environment, register one context for each cluster-manager instance. Name each context after its environment or region, such as `<env>` or `<region>`:

```bash
ackoctl config set-context prod-us \
  --server=https://acm.prod-us.example.com/api \
  --token=$ACKOCTL_TOKEN \
  --workspace-id=prod-us
ackoctl --context=prod-us k8s cluster list
```

Authentication uses bearer tokens. Provide an OIDC JWT obtained through a method such as the Keycloak CLI or a browser device flow. The cluster-manager workspace ACL limits the scope of every call. For non-interactive runs, destructive operations (`delete`, `remove`, mutation `info --allow-write`, and `k8s cluster scale`) also require `--yes`.

The `ackoctl` skill covers installation, configuration, and every command group: connection, cluster, set, record, query, index, note, k8s, info, admin, and udf. See `skills/ackoctl/reference/commands.md` for a concise command reference.

## Prerequisites

### For ACKO skills

- Kubernetes cluster (kind, minikube, EKS, GKE, etc.)
- [ACKO operator](https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator) installed
- `kubectl` configured

### For aerospike-py skills

- Python 3.10+ (aerospike-py requires `>=3.10`; wheels cover 3.10–3.14)
- Running Aerospike server (localhost:3000 by default)

## Benchmark Results

The following results come from evaluating Claude Sonnet on real deployment tasks:

| Metric | with skill | without skill | Improvement |
|--------|-----------|---------------|-------------|
| **Pass Rate** | 100% | 87.5% | +12.5% |
| **Token Usage** | 25,077 | 36,262 | -30.8% |
| **Completion Time** | 73.8s | 137.4s | -46.3% |
| **Tool Calls** | 8.0 | 30.0 | -73.3% |

Key findings:

- The skills prevented the most common CE configuration error: using enterprise-only settings in a CE cluster.
- The skills explained aerospike-py-specific patterns such as NamedTuple access and `Depends` injection.
- Runs with the skills produced seven additional production-oriented features, compared with none in the baseline runs.

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

> The `e2e_pytest/` scenario suite includes a **multi-cluster + Keycloak OIDC** scenario. It covers the common-cluster web application, the dev/prod operator-cluster API, and the bitnami/keycloak realm bootstrap. See the [ACKO multi-cluster docs](https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator/blob/main/docs/multi-cluster-keycloak.md).

## License

MIT
