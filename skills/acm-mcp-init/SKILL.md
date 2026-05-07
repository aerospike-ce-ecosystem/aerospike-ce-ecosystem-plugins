---
name: acm-mcp-init
description: "Register one or many Aerospike Cluster Manager (ACM) MCP endpoints with Claude Code so the cluster-debugger agent and other ecosystem skills can read and operate live clusters. Use when the user wants to set up MCP for ACM, manage multiple ACKO/cluster-manager instances, register additional clusters (multi-cluster ACKO), or troubleshoot a missing endpoint. Triggers on: 'register ACM MCP', 'ACM MCP setup', 'set up Aerospike cluster manager MCP', 'connect plugin to cluster manager', 'add ACKO cluster to claude', 'multi-cluster MCP', '/acm-mcp-init', 'list registered MCP endpoints', 'remove ACM endpoint'."
---

# ACM MCP Setup

Register Aerospike Cluster Manager (ACM) MCP endpoints with Claude Code. ACM exposes 21 Voyager-parity tools (records, query, asinfo, connections) at `/mcp` on its FastAPI port. Each registered endpoint becomes addressable as `mcp__aerospike-<name>__<tool>` — multi-cluster ACKO is handled by registering one endpoint per cluster-manager instance.

This skill works in three modes: **register**, **list**, **remove**. Pick the user intent from their wording, then drive the workflow with `AskUserQuestion`.

---

## Mode 1: Register one or more endpoints

### Step 1 — Establish intent and count

Ask the user how many endpoints to register and gather connection details for each. Use `AskUserQuestion` for the count if it is not in the request:

```
question: "ACM endpoint를 몇 개 등록할까요?"
options:
  - "1 (로컬 dev only)"
  - "2 (dev + prod)"
  - "3 이상 (multi-cluster ACKO)"
```

For each endpoint collect three values, one at a time:

1. **name** (short identifier; becomes the tool prefix). Examples: `dev`, `prod-us`, `staging`.
2. **url** (full HTTP URL to the `/mcp` route). Examples: `http://localhost:8000/mcp`, `https://acm.prod-us.example.com/mcp`.
3. **token** (optional). Skip if the endpoint runs without `ACM_MCP_TOKEN` or relies on OIDC.

Reject names that conflict with `aerospike-*` already registered (run `claude mcp list` to check before adding). If a name collision is detected, propose `<name>-2` or ask the user for a different name.

### Step 2 — Probe each endpoint

Before registering, verify the endpoint is reachable:

```bash
# 200/405/406 means a streamable-http MCP responded; 404 means wrong URL.
curl -fsSL -o /dev/null -w "%{http_code}\n" "$URL" || echo "unreachable"
```

If the probe fails, surface the URL and the HTTP code (or connection error) and ask the user whether to skip or fix the URL. Do not register an unreachable endpoint by default.

If a token was provided, also verify it works:

```bash
curl -fsSL -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" "$URL"
```

### Step 3 — Register via `claude mcp add`

For each validated endpoint:

```bash
# Without auth
claude mcp add --transport http aerospike-${NAME} "${URL}"

# With bearer token
claude mcp add --transport http aerospike-${NAME} "${URL}" \
  --header "Authorization: Bearer ${TOKEN}"
```

Pass the token only as the `--header` value. Never echo or log it. Never write the token into source-controlled files.

### Step 4 — Confirm

```bash
claude mcp list
```

Show the resulting list to the user. Confirm each newly added entry is present.

### Step 5 — Suggest a first prompt

Tell the user how to drive the new endpoints. Example for a `dev` endpoint:

> Try: "in cluster dev, list namespaces and get a sample record from sample_set."

For multi-endpoint registrations, suggest a comparison prompt:

> Try: "compare namespaces between dev and prod-us — flag any sets that exist on one and not the other."

---

## Mode 2: List registered endpoints

When the user asks to see what is registered:

```bash
claude mcp list
```

Filter the output to entries matching `aerospike-*` and report them as a table to the user (name | URL | auth-on?). Include the available tool prefixes (`mcp__aerospike-<name>__*`).

---

## Mode 3: Remove an endpoint

If the user wants to remove an endpoint:

```bash
claude mcp remove aerospike-${NAME}
```

Confirm the removal by listing afterwards. If the user does not give a name, list current entries and ask which to remove.

---

## Re-running the skill

The skill is **idempotent**. Re-running with the same name updates the existing entry — `claude mcp add` rejects duplicates by default, so first remove then re-add:

```bash
claude mcp remove aerospike-${NAME} 2>/dev/null || true
claude mcp add --transport http aerospike-${NAME} "${URL}" [...]
```

Mention this dance to the user before doing it so the audit trail is clear.

---

## Multi-cluster ACKO note

If the user is running multiple `helm install acko` deployments — one per K8s cluster — each Helm release typically also runs its own cluster-manager instance with its own ingress URL. Register each separately:

```
aerospike-dev          → http://localhost:8000/mcp                  (local podman)
aerospike-staging      → https://acm.staging.example.com/mcp        (staging K8s)
aerospike-prod-us      → https://acm.prod-us.example.com/mcp        (prod US)
aerospike-prod-eu      → https://acm.prod-eu.example.com/mcp        (prod EU)
```

The cluster-debugger agent then disambiguates from the user's wording — "in prod-us, …" routes to `mcp__aerospike-prod-us__*`.

For deployments where one cluster-manager fans out to many K8s clusters via kubeconfig contexts, register only that one cluster-manager — context selection happens inside ACM, not at the MCP boundary.

---

## Token storage guidance

If the user pastes a long-lived bearer token, recommend storing it in an OS keychain or env-var manager rather than inline. The header value passed to `claude mcp add` is recorded in `~/.claude/.mcp.json` in plaintext — that file should be treated as a secret.
