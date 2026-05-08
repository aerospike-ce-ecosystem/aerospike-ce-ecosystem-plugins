# Changelog

All notable changes to the `aerospike-ce-ecosystem` Claude Code plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [VERSIONING.md](./VERSIONING.md) for the compatibility matrix and deprecation policy.

## [Unreleased]

### Changed

- **`acko-cluster-debugger` agent → `acko-debugging` skill**: demoted to a skill so triggering happens via description match rather than explicit Task delegation. The 6-step procedure, CE 8.1 pitfalls, and remediation matrix are unchanged; routing through ACM MCP for both data-plane and K8s-plane (the K8s tools shipped in ACM PR #305/#313) is preserved. Subagent context isolation is the only capability lost — most diagnoses are single-shot anyway, and routine reads (`list_k8s_clusters`, `get_k8s_pods`, …) no longer have to spawn a subagent.

### Fixed

- **MCP tool count drift**: `acm-mcp-init` skill now states 27 tools (22 data-plane + 5 K8s-plane) instead of the stale 21.
- **Mutation list completeness**: the demoted `acko-debugging` skill lists all 11 mutation tools, including the `scale_k8s_cluster` entry that was missing from the original 10-name list.

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

[Unreleased]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/releases/tag/v1.0.0
