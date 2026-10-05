# Declarative management with `octeliumctl apply`

Docs: https://octelium.com/docs/octelium/latest/management/core/overview.md

## Check capabilities first

```bash
octeliumctl version
octeliumctl validate --help
octeliumctl apply --help
```

The installed v0.43.0 CLI lacks `validate` and `apply --dry-run`. Both exist in Octelium source
checked on 5 October 2026; use them when the installed CLI supports them. The generated CLI
reference remains a verified v0.43.0 snapshot.

`validate <paths>` checks parsing, unknown fields, enum values, field types, kinds and duplicate
resources locally. It does not contact the Cluster or validate references and server semantics.
`apply --dry-run <paths> [apply flags]` reads current state and computes changes without
mutations. It is not a transaction, does not reserve state and cannot prove the later apply
will succeed. Use exactly the same paths and include/exclude/prune flags for preview and apply.

## What apply does

1. Loads every YAML document from the arguments: files, directories (recursively, `*.yaml`
   and `*.yml`), or `-` for stdin. Each document needs `kind`; `apiVersion: core/v1` is optional.
2. Attempts strict parsing. A field the CLI doesn't know produces
   `Unknown field in the <Kind> Resource at <path>: ...` and **the field is dropped**, not
   rejected. Treat that warning as an error: a typo or a field from a newer release is being
   discarded.
3. Selects kinds. Default: `Config, Policy, IdentityProvider, Namespace, Group, User, Service,
   Credential`. `--include K` (repeatable or comma-separated) replaces that list;
   `--exclude K` removes from it;
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

Current system resources (`metadata.isSystem: true`, e.g. the `default` and `octelium`
Namespaces, the API/Auth/Portal/DNS Services) are excluded from the comparison and prune.
System resources in desired files can still be treated as creates and rejected by the server;
remove them from configuration exports. Resources created at install time but not marked
system (see resource-model.md) are treated like your own.

## Export, edit, apply

```bash
octeliumctl get svc web.prod -o yaml > web.yaml       # full current resource
# edit only what was asked; keep everything else
octeliumctl validate web.yaml
octeliumctl apply --dry-run web.yaml
octeliumctl apply web.yaml
```

For v0.43.0, replace validation and preview with `uv run scripts/validate_resources.py web.yaml`
and `uv run scripts/plan_apply.py web.yaml`. The planner compares metadata display fields and
spec; data and status are intentionally ignored, except that desired Secret data flags an
existing Secret as an update. Use native dry-run to preview data operations where supported.

Single-resource exported YAML contains `status`, `metadata.uid`, `resourceVersion`, timestamps:
apply ignores status and server-managed metadata, so the file can be applied as is. For files kept in Git,
strip those fields and keep `kind`, `metadata.name` (and optional `displayName`,
`description`, `labels`, `annotations`, `tags`), and `spec` (plus `data` for Secret/Config).

## Complete configuration export

A list command (`get svc -o yaml`, for example) returns a wrapper with `items`, not applicable
resource documents. It returns one page: the default is 200 items, the maximum per page is
1,000. Increasing page size does not replace following `listResponseMeta.hasMore`.

From this skill's directory, use the helper to read every page, filter `isSystem` and
`isSystemHidden`, keep names and editable metadata/spec, preserve Config data, and emit a YAML
document per resource plus the ClusterConfig singleton:

```bash
(
  set -euo pipefail
  umask 077
  export_file="$(mktemp ./octelium-config.XXXXXX.yaml)"
  if uv run scripts/export_resources.py --domain <DOMAIN> > "$export_file"; then
    printf '%s\n' "$export_file"
  else
    rm -f "$export_file"
    exit 1
  fi
)
```

Validate the resulting file before using it. The helper writes nothing until all reads succeed;
the export is not a consistent snapshot if resources change during pagination. References in
spec remain portable names; status and server-managed metadata are omitted. To export selected
kinds, use `--include Service,Namespace --skip-cluster-config`.

This is configuration migration, not disaster recovery. It excludes Secrets and Credentials;
Secret values and issued tokens cannot be recovered through the API. It also excludes
Sessions, Devices and Authenticators. Before a reset, establish whether configuration migration
meets the recovery objective. For full recovery, keep a consistent datastore backup, Bootstrap
and installer settings, datastore credentials, TLS certificates and private keys, and encryption
key material where applicable; protect them and test the restore separately. After migration,
re-create Secrets from their source, apply configuration, re-issue Credentials and test admin
login and intended Service access. Review ClusterConfig and references when changing domains.

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
- For GitOps, run native validation and dry-run in CI when supported (the helpers on older
  CLIs), then `octeliumctl apply` on merge. Use a dedicated WORKLOAD User with limited User,
  Group and Credential grants; Credential ALLOWs do not narrow broader inherited grants.

## Pruning safely

Only when the user asks for it, and only when the tree is the complete desired state:

```bash
octeliumctl validate ./octelium
octeliumctl apply --dry-run --prune --include Service --include Namespace ./octelium
uv run scripts/plan_apply.py --prune --include Service --include Namespace ./octelium
# review every DELETE line, then:
octeliumctl apply --prune --include Service --include Namespace ./octelium
```

`plan_apply.py` exits with status 1 and prints `DANGER` lines when the plan deletes install
built-ins (the `root` User, `root-init`, `allow-all`, `essh.octelium`, ...) or every resource of
a kind. Never run the prune when those lines are unexpected.
On older CLIs, use the schema helper for validation and the planner alone for preview.

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
| `scripts/export_resources.py [--include K]` | Paginated, apply-ready configuration export without system resources, Secrets or Credentials. | Read-only `octeliumctl get` |

Validation and planning accept the same path arguments as apply (files, directories, `-`). Run with
`uv run scripts/<name>.py ...` (dependencies declared inline) or `python3` with `pyyaml` and
`jsonschema` installed. Exit codes: validate 0/1 (invalid input)/2 (environment); plan 0/1
(invalid input or dangers)/2 (usage/environment); export 0/2 (usage/environment). After dependency
and argument checks, `--json` returns an `errors` array for loading/environment failures instead of a
traceback; successful validation returns `documents`, successful planning returns the plan.

The schema check proves structure, not meaning: a valid Policy can still grant the wrong access,
and a field valid in the latest schema may be unknown to an older CLI (apply's `Unknown field`
warning catches that).
