---
name: acm-mcp-init
description: "Register one or many Aerospike Cluster Manager (ACM) MCP endpoints with Claude Code so the cluster-debugger agent and other ecosystem skills can read and operate live clusters. Use when the user wants to set up MCP for ACM, manage multiple ACKO/cluster-manager instances, register additional clusters (multi-cluster ACKO), or troubleshoot a missing endpoint. Triggers on: 'register ACM MCP', 'ACM MCP setup', 'set up Aerospike cluster manager MCP', 'connect plugin to cluster manager', 'add ACKO cluster to claude', 'multi-cluster MCP', '/acm-mcp-init', 'list registered MCP endpoints', 'remove ACM endpoint'."
---

# ACM MCP Setup

ACM exposes 21 MCP tools (records, query, asinfo, connections) at `/mcp` on its FastAPI port. Each registered endpoint becomes addressable as `mcp__aerospike-<name>__<tool>`.

For each endpoint collect: **name** (becomes the prefix — e.g. `dev`, `prod-us`), **url** (e.g. `http://localhost:8000/mcp`), **token** (optional bearer, can be empty when OIDC-only or anonymous-on-localhost).

## Server-side auth policy (frequent footgun)

ACM refuses to start with `ACM_MCP_ENABLED=true` on a non-localhost bind interface unless EITHER OIDC is enabled (`OIDC_ENABLED=true` + issuer URL) OR a shared-secret token is configured (`ACM_MCP_TOKEN=...`). Operators who really want anonymous on a sealed network must opt in via `ACM_MCP_ALLOW_ANONYMOUS=true`. "ACM container won't start after enabling the flag" almost always traces back to this rule.

## Probe each URL with an MCP `initialize` POST

A naked `GET /mcp` returns 307/401/405 depending on auth and SDK version, so it does not validate the endpoint. The probe must be a real `initialize` POST — that also exercises the bearer token in the same round-trip.

```bash
INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"acm-mcp-init","version":"0"}}}'

curl -sS -L -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  ${TOKEN:+-H "Authorization: Bearer $TOKEN"} \
  -d "$INIT_BODY" \
  "$URL"
```

Successful payload contains `"serverInfo":{"name":"aerospike-cluster-manager",...}`. Do not register an endpoint whose probe fails auth or returns a non-2xx response.

## Register

```bash
# Without auth
claude mcp add --transport http aerospike-${NAME} "${URL}"

# With bearer token (header value is stored plaintext in ~/.claude/.mcp.json)
claude mcp add --transport http aerospike-${NAME} "${URL}" \
  -H "Authorization: Bearer ${TOKEN}"
```

`claude mcp add` uses a **positional** URL — `--url` is not a valid flag.

`claude mcp add` rejects duplicates, so re-running for an existing name needs an explicit remove first:

```bash
claude mcp remove aerospike-${NAME} 2>/dev/null || true
claude mcp add --transport http aerospike-${NAME} "${URL}" ...
```

`claude mcp list` and `claude mcp remove aerospike-${NAME}` cover the list / remove modes.

## Multi-cluster ACKO patterns

1. **Bundled per-K8s** (default of the ACKO Helm chart): each `helm install acko` ships its own cluster-manager pod with its own ingress URL → register each Helm release separately. Naming convention: `aerospike-<env>` or `aerospike-<region>` (e.g. `aerospike-dev`, `aerospike-prod-us`).
2. **Federated single instance**: one cluster-manager process holds multiple kubeconfig contexts and fans out internally. Register only that one cluster-manager — the cluster-debugger agent picks contexts via tool args, not via MCP prefix.

The agent disambiguates from the user's wording — "in prod-us, …" routes to `mcp__aerospike-prod-us__*`.
