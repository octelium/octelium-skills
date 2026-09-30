# Declarative management with `octeliumctl apply`

Docs: https://octelium.com/docs/octelium/latest/management/core/overview.md

## What apply does (octeliumctl v0.43.0)

1. Loads every YAML document from the arguments: files, directories (recursively, `*.yaml`
   and `*.yml`), or `-` for stdin. Each document needs `kind`; `apiVersion: core/v1` is optional.
2. Parses each document strictly. A field the CLI doesn't know produces
   `Unknown field in the <Kind> Resource at <path>: ...` and **the field is dropped**, not
   rejected. Treat that warning as an error: a typo or a field from a newer release is being
   discarded.
3. Selects kinds. Default: `Config, Policy, IdentityProvider, Namespace, Group, User, Service,
   Credential`. `--include K` (repeatable) replaces that list; `--exclude K` removes from it;
   `--include-secret` adds `Secret`. Documents of other kinds print
   `Skipping the <Kind> <name>. Its kind is not included in this apply operation`.
4. For each selected kind, lists the Cluster's current non-system resources and computes:
   - **create:** in files, not in the Cluster;
   - **update:** in both and different (metadata display fields or spec). The update sends the
     document as the **complete** spec: fields not in the file are reset;
   - **delete** (only with `--prune`): in the Cluster, not in the files, for **every selected
     kind**, even when the paths contain no document of that kind.
5. Creates and updates in kind order (Config → Policy → IdentityProvider → Namespace → Group →
   User → Service → Credential), then prunes in reverse order. A per-resource validation error
   (e.g. a Policy that references a missing Secret) is printed as `Could not create/update ...`
   and **the run continues**, so an apply can partially succeed.
6. If a `ClusterConfig` document is present (any name), replaces the ClusterConfig spec with it,
   regardless of `--include`/`--exclude`.

System resources (`metadata.isSystem: true`, e.g. the `default` and `octelium` Namespaces, the
API/Auth/Portal/DNS Services) are never created, updated or pruned by apply. Resources created
at install time but not marked system (see resource-model.md) are treated like your own.

## Export, edit, apply

```bash
octeliumctl get svc web.prod -o yaml > web.yaml       # full current resource
# edit only what was asked; keep everything else
uv run scripts/validate_resources.py web.yaml
uv run scripts/plan_apply.py web.yaml                  # expect exactly one UPDATE with your fields
octeliumctl apply web.yaml
```

Exported YAML contains `status`, `metadata.uid`, `resourceVersion`, timestamps: apply ignores
status and server-managed metadata, so the file can be applied as is. For files kept in Git,
strip those fields and keep `kind`, `metadata.name` (and optional `displayName`,
`description`, `labels`, `annotations`, `tags`), and `spec` (plus `data` for Secret/Config).

## Recommended repository layout

```text
octelium/
├── cluster-config.yaml          # optional; only if you manage ClusterConfig declaratively
├── namespaces.yaml
├── policies/
├── identity/                    # IdentityProviders, Groups
├── users/
└── services/
    ├── default/
    └── production/
```

- Apply the whole root: `octeliumctl apply ./octelium`. Applying a subdirectory is fine
  **without** `--prune`.
- Keep Secrets out of this tree (create them imperatively, or keep encrypted Secret YAML in a
  separate path applied with `--include-secret`).
- Credentials are usually created imperatively (`create cred`), so a Git tree rarely lists them.
  If you ever prune, exclude Credential (`--exclude Credential`) or every issued token is
  deleted.
- For GitOps, run `plan_apply.py` in CI for review and `octeliumctl apply` on merge, with a
  WORKLOAD User whose Credential has only the Policies it needs.

## Pruning safely

Only when the user asks for it, and only when the tree is the complete desired state:

```bash
uv run scripts/plan_apply.py --prune --include Service --include Namespace ./octelium
# review every DELETE line, then:
octeliumctl apply --prune --include Service --include Namespace ./octelium
```

`plan_apply.py` exits with status 1 and prints `DANGER` lines when the plan deletes install
built-ins (the `root` User, `root-init`, `allow-all`, `essh.octelium`, ...) or every resource of
a kind. Never run the prune when those lines are unexpected.

## Imperative commands

| Command | Notes |
| --- | --- |
| `create secret <name>` | Prompts for the value in a terminal; non-interactively needs `--value`, `--file`, `--from-env` or `-f -`. `--cert/--cert-key` for TLS. |
| `create config <name>` | Same input options; for non-secret configuration data. |
| `create credential [name] --user <u>` | Prints the token once. See identity-and-access.md for flags. |
| `create namespace <name>` | Or declare `kind: Namespace`. |
| `update secret\|config <name>` | Replaces the value (same input options). |
| `update session\|credential\|device\|authenticator ...` | Approve/reject/expire/enable/disable. |
| `delete <kind> <name>` | Immediate, no prompt. Deleting a Namespace, Group or Policy that others reference can break them; check references first (`get ... -o yaml` and grep). |

There are no `create user/group/service/policy/idp` commands: declare those kinds and apply.

## Helper scripts (this skill)

| Script | Purpose | Talks to the Cluster? |
| --- | --- | --- |
| `scripts/validate_resources.py <paths>` | JSON Schema validation (latest published schemas, falls back to the bundled snapshot; `--offline`, `--schema-dir`), duplicate detection, risk warnings (public/anonymous Services, `allow-all`, unconditional ALLOW, plaintext Secret data, ClusterConfig replacement). | No |
| `scripts/plan_apply.py <paths> [apply flags]` | Create/update/delete preview, fields that will be reset, danger detection for prune. | Read-only `octeliumctl get` |

Both accept the same path arguments as apply (files, directories, `-`). Run with
`uv run scripts/<name>.py ...` (dependencies declared inline) or `python3` with `pyyaml` and
`jsonschema` installed. Exit codes: validate 0/1 (errors)/2 (environment); plan 0/1 (dangers)/2.

The schema check proves structure, not meaning: a valid Policy can still grant the wrong access,
and a field valid in the latest schema may be unknown to an older CLI (apply's `Unknown field`
warning catches that).
