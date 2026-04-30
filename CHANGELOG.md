# Changelog

All notable changes to the `aerospike-ce-ecosystem` Claude Code plugin are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See [VERSIONING.md](./VERSIONING.md) for the compatibility matrix and deprecation policy.

## [Unreleased]

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

[Unreleased]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/aerospike-ce-ecosystem/aerospike-ce-ecosystem-plugins/releases/tag/v1.0.0
