# Versioning Policy

The `aerospike-ce-ecosystem` Claude Code plugin uses [Semantic Versioning 2.0.0](https://semver.org/).
Given a version `MAJOR.MINOR.PATCH`:

- **MAJOR** — incompatible skill/agent contract changes, removal of skills, or changes that require user action.
- **MINOR** — new skills/agents/commands, expanded coverage, or backwards-compatible content updates.
- **PATCH** — content corrections, doc fixes, frontmatter tweaks, no behavioural change.

The plugin version is recorded in `.claude-plugin/plugin.json` and tagged in git as `vX.Y.Z`.

## Compatibility Matrix

Each plugin release is validated against specific upstream versions of the projects it documents.
A plugin version is expected to work with the components below; older or newer combinations are best-effort.

| Plugin Version | ACKO | aerospike-py | ackoctl | Aerospike CE Server |
|----------------|------|--------------|---------|---------------------|
| 1.0.0          | v1.0.0 (Helm chart 0.2.0) | 0.7.1 | n/a (ACM MCP)      | 8.1.x (8.x supported) |
| 1.1.0          | v1.0.0 (Helm chart 0.2.0) | 0.7.1 | n/a (ACM MCP)      | 8.1.x (8.x supported) |
| 1.2.0          | v1.2.1 | 0.10.0 | n/a (ACM MCP) | 8.1.x (8.x supported) |
| 2.0.0          | v1.2.1 | 0.10.0 | v0.2.0 (admin/udf/info) | 8.1.x (8.x supported) |
| Unreleased     | tracks ACKO `main` | tracks aerospike-py `main` | tracks ackoctl `main` | 8.x |

Sources for the 1.0.0 row:
- ACKO: latest git tag in `aerospike-ce-kubernetes-operator` (`v1.0.0`); Helm chart `charts/aerospike-ce-kubernetes-operator/Chart.yaml` `version: 0.2.0`.
- aerospike-py: latest git tag in `aerospike-py` (`v0.7.1`).
- Aerospike CE: skills target CE 8.1 (`acko-config-reference`, `acko-deploy`); 8.x line broadly supported.

Notes for the 2.0.0 row:
- The `acm-mcp-init` skill is removed in 2.0.0 — the cluster-manager MCP HTTP server is retired. The new `ackoctl` skill replaces it; the matrix pins `ackoctl >= v0.2.0` because that is the first release with `admin`, `udf`, and `info` parity for the surface previously exposed via MCP.

## Deprecation Policy

- **Minor versions warn.** When a skill is scheduled for removal it is marked deprecated in its frontmatter `description` and in CHANGELOG `Deprecated`. The skill keeps working through the remainder of the current major.
- **Major versions remove.** Deprecated skills/agents/commands are deleted in the next major bump. Renames are handled the same way (old name deprecated for a major, removed at the next).
- **CE feature flags.** Skills that depend on a specific Aerospike CE feature flag (e.g. an 8.x-only config key) are marked in the skill body with the minimum CE version required. If a future CE release drops that feature, the skill is deprecated in the next minor and removed in the next major.
- **Upstream breaks.** A breaking change in ACKO or `aerospike-py` (e.g. CRD `apiVersion` bump, `aerospike-py` API rename) triggers a major plugin release; the matrix row above is the contract for what each plugin version targets.

## Releasing

1. Update `.claude-plugin/plugin.json` version.
2. Move `Unreleased` entries into a new `X.Y.Z` section in `CHANGELOG.md`.
3. Add a new row to the compatibility matrix above.
4. Tag `vX.Y.Z` and push.
