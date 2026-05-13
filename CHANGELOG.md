# Changelog

All notable changes to the `aerospike-ce-ecosystem` Claude Code plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [VERSIONING.md](./VERSIONING.md) for the compatibility matrix and deprecation policy.

## [Unreleased]

## [2.0.0] - 2026-05-13

### BREAKING

- **Removed `acm-mcp-init` skill**: the ACM MCP HTTP server is retired. Users who depended on `claude mcp add --transport http aerospike-...` to talk to cluster-manager must migrate to the [`ackoctl`](https://github.com/aerospike-ce-ecosystem/ackoctl) CLI. The new `ackoctl` skill in this plugin documents the equivalent commands (`ackoctl config set-context` + `ackoctl <noun> <verb>`).

### Added

- **`ackoctl` skill**: documents the [ackoctl](https://github.com/aerospike-ce-ecosystem/ackoctl) Go CLI for cluster-manager. Covers install, kubeconfig-style multi-context configuration, and every command surface — `connection`, `cluster`, `set`, `record`, `query`, `index`, `note`, `k8s`, `info`, `admin`, `udf`. Ships with a per-command reference at `skills/ackoctl/reference/commands.md`.

### Changed

- **`acko-debugging` skill**: diagnostic routing now prefers ackoctl over MCP. The 6-step procedure, CE 8.1 pitfalls, and remediation matrix are unchanged; data-plane and K8s-plane probes route through `ackoctl cluster info` / `ackoctl info exec` / `ackoctl query exec` / `ackoctl k8s cluster get|list` / `ackoctl k8s pod logs` / `ackoctl k8s events list`, falling back to `kubectl`/`asinfo` when ackoctl is unavailable.
- **`acko-cluster-debugger` agent → `acko-debugging` skill**: demoted to a skill so triggering happens via description match rather than explicit Task delegation. Subagent context isolation is the only capability lost — most diagnoses are single-shot anyway, and routine reads (`ackoctl k8s cluster list`, `ackoctl k8s pod logs`, …) no longer have to spawn a subagent.
- **README**: replaced the "MCP integration" section with an "ackoctl integration" section of comparable size. The skills inventory table now lists `ackoctl` in place of `acm-mcp-init`.
- **Plugin manifest**: bumped to `2.0.0` (MAJOR — breaking removal per `VERSIONING.md`).
- **Compatibility matrix**: new 2.0.0 row pinning `ackoctl >= v0.2.0`.

### Migration notes

| Old (1.x with ACM MCP) | New (2.x with ackoctl) |
|------------------------|------------------------|
| `claude mcp add --transport http aerospike-dev http://localhost:8000/mcp` | `ackoctl config set-context dev --server=http://localhost:8000/api --workspace-id=default` |
| `mcp__aerospike-dev__list_namespaces` | `ackoctl cluster info <CONN_ID>` |
| `mcp__aerospike-dev__execute_info` | `ackoctl info exec <CONN_ID> --command='statistics'` |
| `mcp__aerospike-dev__get_k8s_pods` | `ackoctl k8s cluster get <ns>/<name>` |
| `mcp__aerospike-dev__get_k8s_logs` | `ackoctl k8s pod logs <ns>/<name> --pod=<pod> ...` |
| `mcp__aerospike-dev__scale_k8s_cluster` | `ackoctl k8s cluster scale <ns>/<name> --size=N --yes` |

## [1.2.0] - 2026-05-04

### Added

- **Skills**:
  - `acko-e2e-test` — Hybrid pytest rewrite: Python for assertions, bash for CLI orchestration. Tightens release-verification scenarios and reduces flakiness on the CLI orchestration boundary (PR #10).

### CI/CD

- **Daily Release workflow**: New `daily-release.yml` GitHub Actions workflow that auto-detects unreleased commits, computes the next semver from Conventional Commits, and publishes a GitHub release with Claude-generated notes. Mirrors the pattern already used by `aerospike-py` and `aerospike-cluster-manager` so all four ecosystem repos share the same release cadence.

## [1.1.0] - 2026-05-02

### Added

- **Skills**:
  - `acko-e2e-test` — Canonical ACKO end-to-end test playbook for release verification. Documents Ginkgo scenarios, the mandatory `helm install`-based operator setup, and performance checks (PR #6).
- **Skill updates**:
  - `aerospike-py-api` — OTel runtime export check + middleware-null-trace_id note (PR #7).
  - `aerospike-py-fastapi` — API CRUD smoke pattern for the ui-api → DB → Aerospike path (PR #8).

### Changed

- Plugin manifest bumped to `1.1.0` to invalidate stale local plugin caches and surface the new `acko-e2e-test` skill.

## [1.0.0] - 2026-04-30

Initial public release. Plugin manifest version is `1.0.0` (see `.claude-plugin/plugin.json`).

### Added

- **Skills**:
  - `acko-config-reference` — Aerospike CE 8.1 configuration parameters, CRD YAML mapping, and ACKO operator auto-processing rules. Background reference for cluster configuration on Kubernetes.
  - `acko-deploy` — Deploying Aerospike CE on Kubernetes via the ACKO operator. CE-specific YAML templates and constraints that prevent enterprise-only config mistakes.
  - `acko-operations` — Day-2 operations and troubleshooting for existing Aerospike K8s clusters: scaling, rolling upgrades, dynamic config, warm/cold restart, ACL, debugging.
  - `aerospike-py-api` — `aerospike-py` (Rust/PyO3) Python client API reference covering unconventional patterns (module-level exceptions, NamedTuple records, policy constants, expression filters, batch ops, CDT, metrics).
  - `aerospike-py-fastapi` — Production-ready FastAPI patterns for `aerospike-py`: `AsyncClient` lifespan, `Depends` injection, exception-to-HTTP-status mapping, ping health probe, batch endpoints.
- **Agent**:
  - `acko-cluster-debugger` — Systematic debugger agent for ACKO Aerospike clusters; runs an ordered triage procedure when the user reports pod failures, deployment errors, or cluster issues.
- **Plugin manifest**: 1.0.0 release.
  - `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` published for plugin discovery.
  - Repository under `aerospike-ce-ecosystem` GitHub org.

[Unreleased]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.2.0...v2.0.0
[1.2.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/releases/tag/v1.0.0
