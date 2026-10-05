# Contributing

## Principles

1. **Verify against the implementation.** Docs can lag the code. Before stating a behavior
   (flags, defaults, what a command deletes), check `--help` of a release binary and, for
   anything destructive or surprising, the source in
   [octelium/octelium](https://github.com/octelium/octelium). Record version-specific behavior
   with the version ("since v0.40.0").
2. **Keep `SKILL.md` operational and short** (target ≤ ~2.5k tokens, hard limit 500 lines):
   scope and hand-offs, ground rules, workflow, reference routing, sources of truth. Put details
   in `references/` and link every reference file from `SKILL.md`.
3. **Skills are self-contained.** No links outside the skill directory; a skill may name a sibling
   skill as a hand-off, but must work when installed alone. Small duplication between skills is
   acceptable.
4. **Never invent.** Field names come from the JSON Schemas; flags from `--help`; URLs must exist.
   Every Octelium YAML example in the skills is validated against the bundled schemas by CI.
5. **Safety first.** Destructive operations need explicit user consent; never recommend widening
   access to fix a denial; never put secrets in arguments, committed or unprotected files,
   or transcripts.
6. **Descriptions are routing.** Front-load what the skill does and when to use it, name the
   neighbouring skills it should *not* handle, stay under 1024 characters. Update the evals when
   you change a description.

## Release checklist for a new Octelium version

1. Install the release CLIs into a directory:
   `curl -fsSL https://octelium.com/install.sh | VERSION=vX.Y.Z INSTALL_DIR=/tmp/oct USE_SUDO=false bash`.
2. `python3 scripts/generate_cli_reference.py --bin-dir /tmp/oct --version vX.Y.Z` and review the diff.
3. `scripts/sync_schemas.sh` and review the diff (new kinds, fields, enum values).
4. Read the release notes and diff the docs; update references, ground rules, and version notes.
   Re-check the behaviors listed in the README ("Verified against the implementation").
5. If the quick installer changed, update `octelium-quick-install` (options, errors, state files).
6. Bump `metadata.verified-against` in affected skills, and the bundle version in
   `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` and every skill's `metadata.version`.
7. `uv run scripts/validate_repo.py`, `python3 -m unittest discover -s tests`,
   `claude plugin validate --strict .`, and run the evals
   (`claude plugin eval .`), comparing with the previous run.
8. Add a CHANGELOG entry.

## Evals

`evals/` follows the `claude plugin eval` format: one directory per case with `prompt.md` and
`graders/*.md`. Each routing/safety case has a `tool_used` grader on the expected skill and an
`llm` grader with concrete PASS/FAIL criteria; negative cases assert that no Octelium skill loads.
Write prompts the way users talk, without naming the skill.
