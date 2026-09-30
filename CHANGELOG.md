# Changelog

All notable changes to this skill bundle. The bundle is versioned independently of Octelium.

## 0.1.0 (unreleased)

Initial release, verified against Octelium v0.43.0 and quick installer 2.3.

- Skills: `octelium-quick-install`, `octelium-kubernetes-install`, `octelium-cluster-ops`,
  `octelium-management`, `octelium-connect`.
- `octelium-management` helper scripts: `validate_resources.py` (JSON Schema validation, risk
  warnings) and `plan_apply.py` (read-only apply/prune preview).
- Generated CLI references for `octelium`, `octeliumctl` and `octops` v0.43.0; bundled core/v1
  JSON Schema snapshot.
- Claude Code and Codex plugin/marketplace manifests.
- Eval suite (routing, safety, negative cases) and CI (validation, weekly freshness checks).
