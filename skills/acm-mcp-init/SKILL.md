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
question: "How many ACM endpoints to register?"
options:
  - "1 (local dev only)"
  - "2 (dev + prod)"
  - "3 or more (multi-cluster ACKO)"
```

For each endpoint collect three values, one at a time:

1. **name** (short identifier; becomes the tool prefix). Examples: `dev`, `prod-us`, `staging`.
2. **url** (full HTTP URL to the `/mcp` route). Examples: `http://localhost:8000/mcp`, `https://acm.prod-us.example.com/mcp`.
3. **token** (optional). Skip if the endpoint runs without `ACM_MCP_TOKEN` or relies on OIDC.

Reject names that conflict with `aerospike-*` already registered (run `claude mcp list` to check before adding). If a name collision is detected, propose `<name>-2` or ask the user for a different name.

### Step 1.5 — Auth-mode sanity check (server-side)

Before driving the probe in Step 2, remind the user about the ACM server-side rule:

> ACM refuses to start with `ACM_MCP_ENABLED=true` on a non-localhost bind interface unless EITHER OIDC is enabled (`OIDC_ENABLED=true` + issuer URL) OR a shared-secret bearer token is configured (`ACM_MCP_TOKEN=...`). Operators who really want anonymous access on a sealed network must opt in via `ACM_MCP_ALLOW_ANONYMOUS=true`.

If the user reports that "the ACM container won't start" after enabling the flag, this is the most common cause — guide them to set `ACM_MCP_TOKEN` (and re-deploy) before retrying registration.

### Step 2 — Probe each endpoint

A streamable-HTTP MCP server does not respond meaningfully to a naked `GET /mcp` (you'll see 307/401/405 depending on auth and SDK version), so the probe must be an actual `initialize` POST. This validates both reachability AND the bearer token in one round-trip.

```bash
PROBE_AUTH=()
[ -n "$TOKEN" ] && PROBE_AUTH=(-H "Authorization: Bearer $TOKEN")

INIT_BODY='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"acm-mcp-init","version":"0"}}}'

CODE=$(curl -sS -L -o /tmp/acm-init.txt -w "%{http_code}\n" \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  "${PROBE_AUTH[@]}" \
  -d "$INIT_BODY" \
  "$URL")

case "$CODE" in
  200) echo "OK: $(grep -o '\"name\":\"[^\"]*\"' /tmp/acm-init.txt | head -1)" ;;
  401) echo "AUTH-FAIL: bearer token rejected (or none supplied while ACM_MCP_TOKEN is set)" ;;
  404) echo "WRONG-URL: confirm the path includes /mcp and ACM_MCP_ENABLED=true" ;;
  *)   echo "UNEXPECTED: HTTP $CODE — see /tmp/acm-init.txt" ;;
esac
```

The `200` branch parses out the server name from the `serverInfo` payload (expected to be `aerospike-cluster-manager`) so the user gets a positive confirmation rather than a silent green check. On `401`, prompt the user to either supply a token or fix an existing one before continuing — do not register an endpoint that can't authenticate.

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

If the user is running multiple `helm install acko` deployments — one per K8s cluster — they typically have one of two patterns:

1. **Bundled per-K8s** (default of the ACKO chart): each Helm release ships its own cluster-manager pod (`ui.api.enabled=true`). Each cluster-manager instance gets its own ingress URL → register each separately.
2. **Federated single instance** (custom): one cluster-manager process holds multiple kubeconfig contexts and fans out internally. Register only that one cluster-manager — context selection happens inside ACM, not at the MCP boundary.

For pattern 1 the registrations look like:

```
aerospike-dev          → http://localhost:8000/mcp                  (local podman)
aerospike-staging      → https://acm.staging.example.com/mcp        (staging K8s)
aerospike-prod-us      → https://acm.prod-us.example.com/mcp        (prod US)
aerospike-prod-eu      → https://acm.prod-eu.example.com/mcp        (prod EU)
```

The cluster-debugger agent then disambiguates from the user's wording — "in prod-us, …" routes to `mcp__aerospike-prod-us__*`.

---

## Token storage guidance

If the user pastes a long-lived bearer token, recommend storing it in an OS keychain or env-var manager rather than inline. The header value passed to `claude mcp add` is recorded in `~/.claude/.mcp.json` in plaintext — that file should be treated as a secret.
