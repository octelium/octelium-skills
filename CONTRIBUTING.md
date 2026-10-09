# Contributing

## Principles

1. **Verify against the implementation.** Docs can lag the code. Before stating a behavior
   (flags, defaults, what a command deletes), check `--help` of a release binary and, for
   anything destructive or surprising, the source in
   [octelium/octelium](https://github.com/octelium/octelium). Record version-specific behavior
   with the version ("since v0.40.0").
   For Cordium's current workflows, prefer the latest Cordium documentation over older skill
   summaries and source notes; distinguish installed-version differences with the CLI's help.
2. **Keep `SKILL.md` operational and short** (target ≤ ~2.5k tokens, hard limit 500 lines):
   scope and hand-offs, ground rules, workflow, reference routing, sources of truth. Put details
   in `references/` and link every reference file from `SKILL.md`.
3. **Skills are self-contained.** No links outside the skill directory; a skill may name a sibling
   skill as a hand-off, but must work when installed alone. Small duplication between skills is
   acceptable.
4. **Never invent.** Field names come from the JSON Schemas; flags from `--help`; URLs must exist.
   Complete core/v1 examples are checked against the bundled schemas by CI. Explicitly classify
   external resources, fragments and Bootstrap examples (see Validation below).
5. **Safety first.** Preserve the user's authorized target and outcome; prepare a concrete plan
   before asking for missing authorization. Destructive effects need informed consent, not repeated
   prompts for the same approved action. Never recommend widening
   access to fix a denial; never put secrets in arguments, committed or unprotected files,
   or transcripts.
6. **Descriptions are routing.** Front-load what the skill does and when to use it, name the
   neighbouring skills it should *not* handle, stay under 1024 characters. Update the evals when
   you change a description.

## Release checklist for a new Octelium version

1. Install the release CLIs into a directory:
   `curl -fsSL https://octelium.com/install.sh | VERSION=vX.Y.Z INSTALL_DIR=/tmp/oct USE_SUDO=false bash`.
2. `python3 scripts/generate_cli_reference.py --bin-dir /tmp/oct --version vX.Y.Z` and review the diff.
3. `scripts/sync_schemas.sh` and review the diff (fields, enum values). For new kinds, use
   `scripts/sync_schemas.sh --from <complete-local-schema-directory>`.
4. Read the release notes and diff the docs; update references, ground rules, and version notes.
   Re-check the behaviors listed in the README ("Verified against the implementation").
5. If the quick installer changed, update `octelium-quick-install` (options, errors, state files).
   For a Cordium release, install it with
   `curl -fsSL https://octelium.com/install-cordium.sh | VERSION=vX.Y.Z INSTALL_DIR=/tmp/oct bash`,
   run `python3 scripts/generate_cli_reference.py --bin-dir /tmp/oct --version vX.Y.Z --only cordium`
   and `scripts/sync_schemas.sh --set cordium`, then re-check the `cordium` skill's version notes.
6. Bump `metadata.verified-against` (and `metadata.source-checked` where present) in affected
   skills, and the bundle version in root `plugin.json` and every skill's `metadata.version`.
   Run `python3 scripts/generate_plugin_manifests.py` to update the compatibility manifests.
7. `uv run scripts/validate_repo.py`, `python3 -m unittest discover -s tests`,
   `claude plugin validate --strict .`, and run the evals
   with the private, bounded command below, comparing with the previous run.
8. Add a CHANGELOG entry.

## Evals

`evals/` follows the `claude plugin eval` format: one directory per case with `prompt.md` and
`graders/*.md`. Each routing/safety case has a `tool_used` grader on the expected skill and an
`llm` grader with concrete PASS/FAIL criteria; negative cases assert that no Octelium skill loads.
Write prompts the way users talk, without naming the skill.

```bash
claude plugin eval . --no-publish --ablation with-without --runs 3 --max-cost-usd 5
```

This uses model credits; choose the budget and pin `--model`/`--judge-model` for comparable runs.
Reports stay local with `--no-publish`. A cost ceiling is checked between runs and can overrun
by an in-flight run; partial runs aren't comparable to complete results. Cases specify three
repetitions, a turn cap and a 300-second runtime limit. See
[Claude Code evals](https://code.claude.com/docs/en/plugin-evals).

Keep the JSON/HTML report and failure traces private; publish only when sharing is requested.
Record host/model versions, repository revision and local diff, with/without scores, per-run
variation, failures, tokens, time and cost.
The current cases grant only Read/Glob/Grep/Skill and test routing/advice. They don't prove
execution or deployment correctness. `python3 -m unittest discover -s tests` runs separate
execution fixtures with fake CLIs and temporary files, without production credentials.

Execution evals need a separate disposable workspace, synthetic credentials, explicit tool
grants and assertions about files, process cleanup and contacted APIs. Do not grant Bash/Write
to the routing suite or attach production cluster access to test execution. Host discovery and
routing must be measured separately on Codex, Claude Code and Pi; manifest checks alone don't
establish cross-host reliability. Paid evals and live installation tests aren't part of PR CI.

## Plugin metadata

Root `plugin.json` is the maintained identity/version source. Portable clients discover `skills/`
at the root; OpenAI presentation lives in `extensions.com.openai`. That object takes precedence
over the entire Codex compatibility overlay, without merging. Retain `.codex-plugin/plugin.json`
and `.claude-plugin/plugin.json`, generated with `scripts/generate_plugin_manifests.py`; CI checks
them against the root manifest. See [Agent Plugins](https://agent-plugins.org/specification) and
[OpenAI packaging](https://developers.openai.com/plugins/build/plugins).

Installing this skill bundle doesn't authenticate to an Octelium Cluster. No authentication
integration is bundled; the marketplace policy isn't an Octelium login mechanism.

## Validation

Run maintainer checks with Python 3.9+ and `pyyaml`/`jsonschema` installed, or use the scripts'
inline dependencies with `uv`. Offline PR CI runs on Python 3.9 and 3.12; the optional Agent
Skills reference validator runs on 3.12. Weekly freshness checks use the network separately.

| YAML fence | CI check |
| --- | --- |
| `yaml` or `yaml octelium` | Complete core/v1 resource; known kind/API and bundled Draft 4 schema |
| `yaml cordium` | Complete cordium/v1 resource with `kind`; bundled Cordium Draft 4 schema |
| `yaml kubernetes` | Explicit external resource; YAML mapping with API/kind, without Kubernetes schema validation |
| `yaml fragment` | Partial configuration or list; YAML syntax only |
| `yaml bootstrap` | Bootstrap YAML and spec mapping only |

`assets/templates/*.yaml` are validated as `octelium`, except in the `cordium` skill, where they
are validated as `cordium`. CI also parses `assets/bootstrap*.yaml`, including
`bootstrap.example.yaml`. It doesn't validate the Bootstrap's protobuf fields or native
semantics: no safe offline native validator has been verified. Don't run destructive
`octops init` merely to validate an asset. Resource schemas are checked for their declared draft,
schema validity and resolvable local references. Unknown kinds and other APIs in an Octelium or
Cordium example are errors, not silently skipped.

CLI generation verifies the binary's reported version and every help command before updating
any requested output. New snapshots record the executable hash, command count and generator
version; both octops copies must agree. `--check` reports drift without writing references.

When Cordium documentation changes, check the skill's page and section links against the
current docs source checkout. Routes use page frontmatter IDs, which can differ from filenames:

```bash
python3 scripts/validate_cordium_docs.py --docs-dir /path/to/app/docs/cordium/latest
scripts/sync_schemas.sh --set cordium --from /path/to/app/schemas/cordium/latest
```

The link check runs offline and requires PyYAML. It checks Cordium documentation URLs in the
skill's Markdown files, including section anchors, without depending on a live website.
Use the documentation map to route tasks to current pages and worked examples; keep the
generated CLI help explicitly scoped to its recorded version.

Schema sync validates and stages the complete set: core/v1 for `octelium-management` and
cordium/v1 for `cordium` (`--set` selects one; remote sync defaults to both, `--from` to
`octelium`). Local `--from` discovers new kinds and rejects a source missing bundled kinds;
review removals manually. Remote sync checks the currently bundled kinds, because no
authoritative remote inventory has been verified. Comparison is semantic, avoiding
formatting-only drift. Exit 1 means drift in `--check`; exit 2 means an unavailable source or
invalid input, not proven drift.

Updates restore previous files/schemas after a checked replacement failure. Directory replacement
uses a backup and two renames, not a crash-atomic filesystem transaction. If forcibly killed or
restoration fails, retain/recover the `.octelium-schema-backup-*` directory before retrying.
