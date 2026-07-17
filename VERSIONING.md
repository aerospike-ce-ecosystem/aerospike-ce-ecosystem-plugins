# Versioning Policy

The `aerospike-ce-ecosystem` Claude Code plugin follows [Semantic Versioning 2.0.0](https://semver.org/). For a version in the form `MAJOR.MINOR.PATCH`:

- **MAJOR** — incompatible skill/agent contract changes, removal of skills, or changes that require user action.
- **MINOR** — new skills/agents/commands, expanded coverage, or backwards-compatible content updates.
- **PATCH** — content corrections, doc fixes, frontmatter tweaks, no behavioural change.

The plugin version is recorded in `.claude-plugin/plugin.json` and tagged in git as `vX.Y.Z`.

## Compatibility Matrix

Each plugin release is validated against specific versions of the upstream projects it documents. The plugin is expected to work with the combinations below; other combinations are best-effort.

| Plugin Version | ACKO | aerospike-py | ackoctl | Aerospike CE Server |
|----------------|------|--------------|---------|---------------------|
| 1.0.0          | v1.0.0 (Helm chart 0.2.0) | 0.7.1 | n/a (ACM MCP)      | 8.1.x (8.x supported) |
| 1.1.0          | v1.0.0 (Helm chart 0.2.0) | 0.7.1 | n/a (ACM MCP)      | 8.1.x (8.x supported) |
| 1.2.0          | v1.2.1 | 0.10.0 | n/a (ACM MCP) | 8.1.x (8.x supported) |
| Unreleased     | tracks ACKO `main` | tracks aerospike-py `main` | tracks ackoctl `main` | 8.x |

The 1.0.0 row is based on these sources:

- ACKO: latest git tag in `aerospike-ce-kubernetes-operator` (`v1.0.0`); Helm chart `charts/aerospike-ce-kubernetes-operator/Chart.yaml` `version: 0.2.0`.
- aerospike-py: latest git tag in `aerospike-py` (`v0.7.1`).
- Aerospike CE: skills target CE 8.1 (`acko-config-reference`, `acko-deploy`); 8.x line broadly supported.

## Deprecation Policy

- **Minor versions warn.** When a skill is scheduled for removal, its frontmatter `description` and the `Deprecated` section of the CHANGELOG mark it as deprecated. The skill continues to work for the rest of the current major version.
- **Major versions remove.** The next major release removes deprecated skills, agents, and commands. Renames follow the same process: the old name remains deprecated for the current major version and is removed in the next one.
- **CE feature flags.** A skill that depends on a specific Aerospike CE feature flag, such as an 8.x-only configuration key, states the minimum required CE version in its body. If a future CE release removes that feature, the skill is deprecated in the next minor release and removed in the next major release.
- **Upstream breaks.** A breaking change in ACKO or `aerospike-py`, such as a CRD `apiVersion` bump or an `aerospike-py` API rename, triggers a major plugin release. Each compatibility-matrix row defines the upstream versions targeted by that plugin release.

## Releasing

1. Update the version in `.claude-plugin/plugin.json`.
2. Move `Unreleased` entries into a new `X.Y.Z` section in `CHANGELOG.md`.
3. Add a new row to the compatibility matrix above.
4. Tag `vX.Y.Z` and push.
