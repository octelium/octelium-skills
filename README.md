# Octelium Agent Skills

Official [Agent Skills](https://agentskills.io) for [Octelium](https://octelium.com), the open
source, self-hosted zero trust secure access platform. They teach AI coding agents (Claude Code,
OpenAI Codex, and any agent that supports the Agent Skills format) to install, operate, manage
and use Octelium Clusters correctly and safely.

## Skills

| Skill | Use it to | Main tools |
| --- | --- | --- |
| [`octelium-quick-install`](skills/octelium-quick-install/SKILL.md) | Install, resume, repair or remove a single-node Cluster on one Linux VM with the official quick installer; DNS, TLS and first login | `install-cluster.sh`, `octops cert` |
| [`octelium-kubernetes-install`](skills/octelium-kubernetes-install/SKILL.md) | Install a production Cluster on existing (multi-node) Kubernetes: node roles, CNI/Multus, datastores, Bootstrap, `octops init`, DNS, TLS | `octops init`, `kubectl` |
| [`octelium-cluster-ops`](skills/octelium-cluster-ops/SKILL.md) | Upgrades, certificates, packages, health checks, nodes/Gateways, access recovery, uninstall | `octops`, `kubectl` |
| [`octelium-management`](skills/octelium-management/SKILL.md) | Services, Policies, Users, Groups, IdentityProviders, Credentials, Sessions, Secrets, ClusterConfig | `octeliumctl` |
| [`octelium-connect`](skills/octelium-connect/SKILL.md) | Log in, connect, publish and serve Services, eSSH, containers/Kubernetes/CI clients, client troubleshooting | `octelium` |

Each skill is self-contained (`SKILL.md` plus on-demand `references/`, and for management
`scripts/` and `assets/`), so skills can be installed individually or together.

## Install

### Claude Code

```bash
claude plugin marketplace add octelium/octelium-skills
claude plugin install octelium@octelium
```

Or inside a session: `/plugin marketplace add octelium/octelium-skills`, then
`/plugin install octelium@octelium`. Skills are namespaced as `octelium:<skill>`.

### OpenAI Codex

```bash
codex plugin marketplace add octelium/octelium-skills
```

Then install the **Octelium** plugin from that marketplace in the Codex plugin browser (`/plugins`).

### Other agents

Any agent that reads the Agent Skills format can use the directories under `skills/` directly,
for example with the [`skills`](https://skills.sh) CLI:

```bash
npx skills add octelium/octelium-skills
```

or by copying/symlinking `skills/<skill-name>` into the agent's skills directory (e.g.
`~/.claude/skills/`, or `.agents/skills/` in a repository for agents that read that location).

### Requirements

The skills drive the real CLIs: `octelium`, `octeliumctl`, `octops`
(`curl -fsSL https://octelium.com/install.sh | bash`), plus `kubectl` for Kubernetes work. The
management helper scripts need Python 3.9+ with `pyyaml` and `jsonschema`; with
[uv](https://docs.astral.sh/uv/) they run as `uv run <script>` and install their own dependencies.

## How the skills are designed

- **Workflows and judgment in `SKILL.md`, facts in references.** Each `SKILL.md` stays small (about
  1k to 2k tokens): scope and hand-offs, ground rules, the workflow, and a routing table to reference
  files that agents load only when needed.
- **Verified against the implementation.** Behaviors were checked against the Octelium source and
  v0.43.0 binaries, not only the prose docs. Examples: `octeliumctl apply` replaces whole resources;
  `apply --prune` deletes missing resources of *every* included kind (including
  the built-in `root` User, `root-init` Credential and `allow-all` Policy); `octops init` deletes an
  existing `octelium` namespace and wipes the datastores it is given; `octops` confirmation prompts
  are skipped when there is no TTY; web login blocks waiting for a browser.
- **Native checks and supporting tools.** Prefer `octeliumctl validate` and
  `octeliumctl apply --dry-run` when the installed CLI supports them. Both were confirmed in
  Octelium source on 5 October 2026; the installed v0.43.0 binary lacks them. Validation is
  local; dry-run reads current state without mutations and does not guarantee server acceptance.
  `octelium-management` also ships
  `scripts/validate_resources.py` (validates YAML against the published JSON Schemas; `apply` only
  warns and drops unknown fields) and `scripts/plan_apply.py` (read-only preview of what `apply`
  would create, replace and prune, flagging dangerous deletions), plus `scripts/export_resources.py`
  (paginated, apply-ready configuration export). The planner compares metadata and spec;
  data and status are intentionally ignored except for the Secret update marker.
- **Sources of truth, in order:** the installed CLI's `--help` for syntax; the JSON Schemas at
  `https://octelium.com/schemas/octelium/latest/core.v1.<Kind>.schema.json` for resource structure;
  the docs index `https://octelium.com/docs/octelium/latest/llms.txt` (every page has a `.md` twin)
  for current behavior; the bundled references as an offline snapshot.
- **Safety rules, not a security boundary.** The skills keep agents conservative (no access
  broadening to "fix" denials, no secrets in arguments or unprotected files, explicit consent
  for destructive flags, no interactive logins run by the agent). What an agent can actually do is decided by
  Octelium's own authentication and Policies, and by the credentials the user gives it.

## Compatibility and versioning

- Root `plugin.json` follows the portable [Agent Plugins format](https://agent-plugins.org/specification).
  OpenAI presentation is under `extensions.com.openai`; derived Codex and Claude compatibility
  manifests are retained. Installation doesn't log in to an Octelium Cluster.
- The skill bundle is versioned independently of Octelium (semver, see [CHANGELOG.md](CHANGELOG.md)).
- Each skill records what it was verified against in `metadata.verified-against`
  (currently Octelium v0.43.0 and quick installer 2.3). Newer Octelium versions are expected to
  work; version-specific behavior is called out in the references.
- The generated CLI references (`references/cli-*.md`) and the JSON Schema snapshot are refreshed
  per Octelium release; a weekly CI job reports drift.

## Repository layout

```text
plugin.json              Portable plugin manifest and shared metadata source
.claude-plugin/          Claude Code plugin manifest + marketplace (plugin = repository root)
.codex-plugin/           Codex plugin manifest
.agents/plugins/         Codex marketplace
skills/<name>/           The skills (Agent Skills format)
evals/                   Routing, safety and negative test cases (`claude plugin eval` format)
scripts/                 Maintainer tooling: validation, CLI reference generation, schema sync
tests/                   Helper, protected workflow and maintenance regression tests
.github/workflows/       CI: validation on every change, weekly freshness checks
```

## Development

```bash
uv run scripts/validate_repo.py                     # spec, links, manifests, YAML examples vs schemas, evals
python3 -m unittest discover -s tests
python3 scripts/generate_plugin_manifests.py [--check]
python3 scripts/generate_cli_reference.py --bin-dir <dir-with-release-binaries> --version vX.Y.Z
scripts/sync_schemas.sh [--check]                   # refresh/check the bundled JSON Schemas
claude plugin validate --strict .                   # Claude Code manifest checks
claude plugin eval . --no-publish --runs 3 --max-cost-usd 5
```

Model evals use credits; choose the budget. They test routing/advice, while the offline tests
exercise helpers and maintenance behavior. See CONTRIBUTING for limits and private reports.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the release checklist and writing guidelines.

## License

Apache License 2.0. See [LICENSE](LICENSE).
