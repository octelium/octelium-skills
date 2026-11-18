# Changelog

All notable changes to this skill bundle. The bundle is versioned independently of Octelium.

## 0.1.0 (unreleased)

Initial release, verified against Octelium v0.51.0, quick installer 2.3 and Cordium v0.20.0.

- Skills: `octelium-quick-install`, `octelium-kubernetes-install`, `octelium-cluster-ops`,
  `octelium-management`, `octelium-connect`, `cordium`.
- `cordium`: installing the Cordium package, Workspaces for developers, AI agents and CI,
  Workspace/Template YAML, Spaces, Templates and pre-builds, Secrets, GitProviders, storage and
  the Cordium ClusterConfig, checked against current Cordium documentation and source;
  `scripts/validate_resources.py`, the generated `cordium` v0.20.0 CLI reference and
  the bundled cordium/v1 JSON Schema snapshot.
- `octelium-management` helper scripts: `validate_resources.py` (JSON Schema validation, risk
  warnings), `plan_apply.py` (read-only apply/prune preview) and `export_resources.py`
  (paginated configuration export).
- Native validation/dry-run guidance for v0.44.0+, with fallback workflows for older clients;
  strict helper parsing and regression tests.
- Corrected Policy priorities, Credential scope guidance, recovery decisions, protected token
  and backup handling, PostgreSQL verification defaults and GitHub OIDC subject examples.
- Generated CLI references for `octelium`, `octeliumctl` and `octops` v0.51.0; bundled core/v1
  JSON Schema snapshot refreshed from the current website, including Device/Session evidence,
  posture, probing and AccessLog network fields.
- File-based authentication/access tokens (v0.51.0+), Service type filters (v0.50.0+), daemon
  owner policies, detached connection diagnostics, rootless UDP serving and SFTP user selection.
- Resumable initialization and Genesis Job tracking (v0.50.0+), with legacy reset warnings,
  installer marker recovery guidance and protected token-file login examples.
- DNS zones and Gateway/Region hostname migration, current browser/desktop access, live demo,
  Enterprise installation/customer portal links and Markdown discovery indexes.
- Documentation link checks for both Octelium and Cordium, including frontmatter-only indexes.
- Claude Code and Codex plugin/marketplace manifests.
- Eval suite (routing, safety, negative cases) and CI (validation, weekly freshness checks).
