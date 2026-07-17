# Changelog

All notable changes to the `aerospike-ce-ecosystem` Claude Code plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [VERSIONING.md](./VERSIONING.md) for the compatibility matrix and deprecation policy.
Per-release notes are also auto-published to [GitHub Releases](https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/releases) by the `daily-release.yml` workflow.

## [Unreleased]

### Changed

- The `aerospike-py-api` skill now documents the `.result_code: int` attribute on Aerospike exceptions. Server errors carry the actual wire code, such as `FailForbidden`=22, while client-side errors use the `-1` `CLIENT_SIDE_RESULT_CODE` sentinel. Applications can use this structured value instead of parsing error messages (aerospike-py ADR-0027, PR #413).
- The plugin manifest (`plugin.json`) and `marketplace.json` descriptions now cover all nine current skills.
- The CI workflow prompts (`issue-planner`, `agent-implement`, `pr-reviewer`) now reflect the current nine-skill layout instead of the obsolete "5 skills + 1 agent" structure.
- The Skills table in `README.md` now includes the previously missing `acko-e2e-test` and `bug-reporter` skills.

### Fixed

- Removed the phantom `DynamicConfigRecovered` event from `acko-operations/reference/events.md` and `acko-debugging/SKILL.md` — the ACKO operator emits no event when `ConfigDegraded` resolves (`internal/controller/events.go` defines no such reason); recovery is observed via `status.phase` returning to `Completed` and the `DynamicConfigDegraded` condition being removed.
- Corrected stale `ackoctl` verbs (`k8s pod logs` → `k8s cluster logs`, `udf register` → `udf upload`) and CE 7.x namespace parameters (`stop-writes-pct` → `stop-writes-sys-memory-pct`, `high-water-*-pct` → `evict-used-pct`) in command examples across `acko-debugging`, `ackoctl`, `acko-operations`, and `README.md`.
- Replaced `ackoctl k8s events list` with `ackoctl k8s cluster events`, matching the actual location of the events verb under the `k8s cluster` noun (`ackoctl/SKILL.md`, `acko-debugging/SKILL.md`, `README.md`).
- Corrected the `cluster configure-namespace` flags in `ackoctl/reference/commands.md` from `--namespace`/`--set` to the repeatable `--name`/`--param` flags used by `ackoctl/SKILL.md` and the CLI.
- Updated the aerospike-py prerequisite in `README.md` from "Python 3.9+" to "Python 3.10+", matching the package declaration `requires-python = ">=3.10"`.
- Shortened the `description` frontmatter for the `acko-e2e-test` and `acko-debugging` skills to keep it below the 1024-character loading limit.

### Removed

- Deleted the unused `.mcp.json` placeholder left by the retired `acm-mcp-init` MCP integration.

## [1.4.4] - 2026-05-17

### Fixed

- Skills — corrected `ackoctl` verbs/flags and added an `aerospike-py` import note (#35).

## [1.4.3] - 2026-05-15

### Changed

- Skills — trimmed redundant and generic content from 4 skills (#32).

### CI/CD

- Daily Release now runs at KST 07:00 (#31).

## [1.4.2] - 2026-05-13

### Changed

- Reverted the erroneous 2.0.0 release because replacing the MCP HTTP server with `ackoctl` is a feature swap, not a breaking major change (#30).

## [1.4.1] - 2026-05-13

### Fixed

- `ackoctl` skill — aligned the documented commands with the actual `ackoctl` CLI (#29).

## [1.4.0] - 2026-05-13

### Added

- **Skills**:
  - `ackoctl` — drive `aerospike-cluster-manager` through the `ackoctl` Go CLI (connections, records, queries, indexes, operator notes, K8s `AerospikeCluster` CRs, admin, UDFs) (#27).
  - `bug-reporter` — routes ACKO / ecosystem bug reports to the correct repo and generates a ready-to-paste GitHub issue body (#28).

### Removed

- Retired the `acm-mcp-init` skill and the cluster-manager MCP HTTP server integration; `ackoctl` provides equivalent coverage (#27).

## [1.3.1] - 2026-05-08

### Changed

- Demoted the `acko-cluster-debugger` agent to the `acko-debugging` skill and trimmed ~206 LOC of cross-skill duplication (#21).

### Removed

- The `agents/` directory — the plugin no longer ships agents (#21).

## [1.3.0] - 2026-05-07

### Added

- **Skills**:
  - `acm-mcp-init` — cluster-manager MCP server initialisation, plus an MCP-aware `acko-cluster-debugger` (#19). _(Retired in 1.4.0.)_

## [1.2.2] - 2026-05-06

### CI/CD

- Daily Release now limits automatic version bumps to minor (`feat`) and patch releases; major bumps remain manual (#18).

## [1.2.1] - 2026-05-06

### Added

- **Tests**:
  - `e2e` — multi-cluster + Keycloak OIDC pytest scenarios: common-cluster web, dev/prod operator-cluster API, and keycloak realm bootstrap (#17).

## [1.2.0] - 2026-05-04

### Changed

- **Skills**:
  - `acko-e2e-test` — rewritten as a hybrid pytest suite, using Python for assertions and bash for CLI orchestration. The change tightens release-verification scenarios and reduces flakiness at the CLI orchestration boundary (PR #10).
- **Skill updates**:
  - `aerospike-py-api` — added a PK regex filter scan guide and `REGEX_*` constants (PR #11); cross-linked the Secondary Index alternative from the PK regex notes (PR #14).

### CI/CD

- **Daily Release workflow**: Added the `daily-release.yml` GitHub Actions workflow. It detects unreleased commits, calculates the next semver version from Conventional Commits, and publishes a GitHub release with Claude-generated notes. The workflow follows the pattern used by `aerospike-py` and `aerospike-cluster-manager`, giving all four ecosystem repositories the same release cadence.

## [1.1.0] - 2026-05-02

### Added

- **Skills**:
  - `acko-e2e-test` — Canonical ACKO end-to-end test playbook for release verification. Documents Ginkgo scenarios, the mandatory `helm install`-based operator setup, and performance checks (PR #6).
- **Skill updates**:
  - `aerospike-py-api` — OTel runtime export check + middleware-null-trace_id note (PR #7).
  - `aerospike-py-fastapi` — API CRUD smoke pattern for the ui-api → DB → Aerospike path (PR #8).

### Changed

- Bumped the plugin manifest to `1.1.0` so stale local plugin caches are invalidated and the new `acko-e2e-test` skill becomes visible.

## [1.0.0] - 2026-04-30

Initial public release. The plugin manifest version is `1.0.0` (see `.claude-plugin/plugin.json`).

### Added

- **Skills**:
  - `acko-config-reference` — Aerospike CE 8.1 configuration parameters, CRD YAML mapping, and ACKO operator auto-processing rules. Background reference for cluster configuration on Kubernetes.
  - `acko-deploy` — Deploying Aerospike CE on Kubernetes via the ACKO operator. CE-specific YAML templates and constraints that prevent enterprise-only config mistakes.
  - `acko-operations` — Day-2 operations and troubleshooting for existing Aerospike K8s clusters: scaling, rolling upgrades, dynamic config, warm/cold restart, ACL, debugging.
  - `aerospike-py-api` — `aerospike-py` (Rust/PyO3) Python client API reference covering unconventional patterns (module-level exceptions, NamedTuple records, policy constants, expression filters, batch ops, CDT, metrics).
  - `aerospike-py-fastapi` — Production-ready FastAPI patterns for `aerospike-py`: `AsyncClient` lifespan, `Depends` injection, exception-to-HTTP-status mapping, ping health probe, batch endpoints.
- **Agent**:
  - `acko-cluster-debugger` — Systematic debugger agent for ACKO Aerospike clusters; runs an ordered triage procedure when the user reports pod failures, deployment errors, or cluster issues. _(Demoted to the `acko-debugging` skill in 1.3.1.)_
- **Plugin manifest**: 1.0.0 release.
  - `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` published for plugin discovery.
  - Repository under `aerospike-ce-ecosystem` GitHub org.

[Unreleased]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.4.4...HEAD
[1.4.4]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.4.2...v1.4.3
[1.4.2]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.4.1...v1.4.2
[1.4.1]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.3.1...v1.4.0
[1.3.1]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.3.0...v1.3.1
[1.3.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.2.2...v1.3.0
[1.2.2]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/releases/tag/v1.0.0
