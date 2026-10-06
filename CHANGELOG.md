# Changelog

All notable changes to this skill bundle. The bundle is versioned independently of Octelium.

## 0.1.0 (unreleased)

Initial release, verified against Octelium v0.43.0, quick installer 2.3 and Cordium v0.15.0.

- Skills: `octelium-quick-install`, `octelium-kubernetes-install`, `octelium-cluster-ops`,
  `octelium-management`, `octelium-connect`, `cordium`.
- `cordium`: installing the Cordium package, Workspaces for developers, AI agents and CI,
  Workspace/Template YAML, Spaces, Templates and pre-builds, Secrets, GitProviders, storage and
  the Cordium ClusterConfig, checked against the Cordium source (cc4af4b) with corrections to
  the docs; `scripts/validate_resources.py`, the generated `cordium` v0.15.0 CLI reference and
  the bundled cordium/v1 JSON Schema snapshot.
- `octelium-management` helper scripts: `validate_resources.py` (JSON Schema validation, risk
  warnings), `plan_apply.py` (read-only apply/prune preview) and `export_resources.py`
  (paginated configuration export).
- Native validation/dry-run guidance based on source checked on 5 October 2026, with v0.43.0
  fallback workflows; strict helper parsing and regression tests.
- Corrected Policy priorities, Credential scope guidance, recovery decisions, protected token
  and backup handling, PostgreSQL verification defaults and GitHub OIDC subject examples.
- Generated CLI references for `octelium`, `octeliumctl` and `octops` v0.43.0; bundled core/v1
  JSON Schema snapshot.
- Claude Code and Codex plugin/marketplace manifests.
- Eval suite (routing, safety, negative cases) and CI (validation, weekly freshness checks).
