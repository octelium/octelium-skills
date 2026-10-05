---
name: octelium-management
description: >-
  Manage the resources of a running Octelium Cluster with octeliumctl: Services (HTTP, SSH,
  PostgreSQL, MySQL, Kubernetes, TCP/UDP, DNS, SOCKS5, RDP, MCP, LLM; public/anonymous, secretless
  upstream credentials, managed containers, dynamic config), Users, Groups, Namespaces, Policies
  and access control (CEL/OPA conditions, priorities, inline and global Policies),
  IdentityProviders (GitHub, OIDC, SAML, workload OIDC assertions), Credentials, Sessions,
  Secrets and ClusterConfig. Use when creating, changing, auditing or deleting Cluster resources,
  granting or revoking access, writing Policy YAML, or running `octeliumctl apply/get/create/
  update/delete`. Not for connecting as a client (octelium-connect), installing a Cluster
  (octelium-quick-install, octelium-kubernetes-install), or upgrades, TLS certificates and
  Kubernetes-level operations (octelium-cluster-ops).
license: Apache-2.0
compatibility: Requires octeliumctl logged in to the Cluster with API access. Helper scripts need Python 3.9+ with PyYAML and jsonschema (or uv).
metadata:
  author: Octelium Labs, LLC
  version: "0.1.0"
  verified-against: octelium v0.43.0
  source-checked: octelium fe628332 (2026-10-05)
---

# Octelium: manage Cluster resources

Octelium resources (Core API `core/v1`) live in the Cluster's own API, not in Kubernetes.
They are managed declaratively with `octeliumctl apply` (like `kubectl apply`) plus a few
imperative commands. Every access decision is made by _Policies_: there is no built-in
superuser, and nothing is reachable unless a Policy allows it.

## Scope

- **Use for:** authoring and applying resource YAML, access control, identity
  (Users/Groups/IdPs/Credentials/Sessions/Devices), Secrets, ClusterConfig, auditing current
  state, diagnosing "why is X denied".
- **Hand off:** client connection and access problems → **octelium-connect**. Upgrades, TLS
  certificates, Cluster health, `kubectl`-level work → **octelium-cluster-ops**. No Cluster yet
  → an install skill.

## Ground rules

Check the installed CLI's capabilities; the bundled CLI reference is v0.43.0. Follow these
rules while preserving the user's authorized target and outcome. Prepare the concrete change
and preview first; ask only for missing inputs or unresolved destructive scope.

1. **Look before you change.** `octeliumctl get <kind> <name> -o yaml` for every resource you
   touch, and the Policies involved. Never assume a resource's current content.
2. **`apply` replaces whole resources.** Each document is the complete desired spec; any field
   you omit is reset. To edit an existing resource, export it, change only what was asked,
   and apply the full document. ClusterConfig is the same: its entire spec is replaced.
3. **Validate and preview before apply.** Check `octeliumctl validate --help` and
   `octeliumctl apply --help`. When supported, use `validate <paths>` and
   `apply --dry-run <paths> [same flags as apply]`. Validation is local; dry-run reads current
   state, skips mutations and does not guarantee server acceptance or reserve state. On older
   CLIs, use `scripts/validate_resources.py` and `scripts/plan_apply.py` with `uv run` or
   `python3`. Resolve helper paths against the loaded skill directory, keeping the user's project
   as the working directory so resource paths still refer to it. The helpers add risk warnings
   and field-level previews. Apply still drops unknown fields with a warning and can skip rejected resources
   while applying the rest. Read its output for partial success.
4. **`--prune` is destructive across kinds.** It deletes every non-system resource of *each
   included kind* that isn't in the given paths, including kinds with no documents there. A
   bare `octeliumctl apply --prune ./services/` would delete all Users, Groups, Policies,
   IdentityProviders, Namespaces, Credentials and Configs, including the built-in `root` User,
   the `root-init` Credential and the `allow-all` Policy. Use `--prune` only when the user asks
   and the paths are the complete source of truth for the kinds you restrict it to with
   `--include`; preview with native dry-run when supported and run `plan_apply.py --prune`
   with the same flags for danger detection. Show the deletions first.
5. **Never widen access to fix a denial.** Don't attach `allow-all`, add `matchAny` ALLOW rules,
   disable Policies, remove DENY rules, or set `isPublic`/`isAnonymous` to make something work,
   unless the user explicitly asks for that exact change. Diagnose (references/policies.md),
   then propose the narrowest rule and say who gains what.
6. **Keep secrets out of ordinary files, arguments and output.** Don't put secret values in
   committed or unprotected YAML, `--value` arguments or chat. Have the user run `octeliumctl create secret <name>`
   (interactive prompt) in their terminal, or use `--file <path>`, `--from-env VAR` or stdin
   (`-f -`). Reference Secrets by name (`fromSecret: <name>`). New Credential tokens are shown
   once: have the user create them in their terminal, or capture output to an authorized private
   file without reading its contents into the transcript (references/identity-and-access.md).
7. **Don't lock the admins out.** Before deleting or changing `root`, `root-init`, `allow-all`,
   admin Users/Groups, IdentityProviders, or Policies on the `octelium-api` Namespace, confirm
   another admin identity exists and works (e.g. `octeliumctl get user <admin>` and a test
   login by that admin).
8. **Deletes and updates have no confirmation prompt.** `octeliumctl delete ...`, `update
   session --reject`, `update credential --disable` act immediately. State exactly what will
   happen and proceed if the user already authorized that target and outcome; ask only when
   the scope or destructive effect remains unresolved.
9. **Don't invent fields, enum values, names or references.** Take field names from the JSON
   Schema of the kind (references/resource-model.md lists the URLs); take names from `get`.

In helper command examples, `octelium_skill_dir` is the absolute directory containing this
loaded `SKILL.md`. Resolve it from the agent's skill location; don't change the project's working
directory. For example: `uv run "$octelium_skill_dir/scripts/validate_resources.py" desired.yaml`.

## Workflow

1. **Context.** Domain (`OCTELIUM_DOMAIN` or `--domain`), CLI version (`octeliumctl version`),
   authentication (octeliumctl shares the `octelium` Session; if none exists, the user must log
   in: see the octelium-connect skill). Reuse authorized access; a diagnostic request doesn't
   authorize reading tokens or starting browser login. Bound the first harmless API call with
   the agent's command timeout. Use `timeout 30 octeliumctl get ns` only if GNU `timeout` is
   available; on other hosts use the agent's equivalent and stop only the process you started.
2. **Find the source of truth.** Ask whether the Cluster is managed from a Git directory of YAML.
   If so, edit those files instead of creating drift, and apply from there.
3. **Inspect** current resources (`get ... -o yaml`), including every Policy that affects the
   request path (Service, Namespace, User, Groups, ClusterConfig global Policies).
4. **Author** the smallest change. Start from exported YAML for existing resources; use
   `assets/templates/` and the references for new ones; check fields against the schema.
5. **Validate** with native `octeliumctl validate` when supported, or
   `scripts/validate_resources.py` on older CLIs. Use the helper for additional risk warnings.
   Fix every error; review every warning.
6. **Preview** with native `octeliumctl apply --dry-run` when supported, or
   `scripts/plan_apply.py` on older CLIs, using the same paths and flags you will apply. Show
   the user the plan when it updates or deletes anything, touches Policies or identity, or
   exposes a Service publicly.
7. **Apply** exactly what was previewed: `octeliumctl apply <paths> [flags]`. Read the output for
   `Unknown field`, `Could not create`, `Could not update` and `Skipping` lines.
8. **Verify** with `get`, and for access changes, a real request by the intended User (or ask
   the user to test).
9. **Report** what changed, what access it grants or removes, and how to revert.

## Command map

| Task | Command |
| --- | --- |
| Apply desired state | `octeliumctl apply <file-or-dir>... [--include K] [--exclude K] [--include-secret] [--prune]`; `-` reads stdin |
| Validate / preview (when supported) | `octeliumctl validate <paths>`; `octeliumctl apply --dry-run <paths> [apply flags]` |
| Read | `octeliumctl get <kind> [name] [-o yaml\|json]`; list flags `--page`, `--items-per-page`, `--order-by-name`, `--order-reverse`; filters `get svc --namespace`, `get cred\|sess\|dev\|authn --user` |
| Kinds for `get` | `service svc`, `namespace ns`, `user usr`, `group grp`, `policy pol`, `identityprovider idp`, `credential cred`, `session sess`, `device dev`, `authenticator authn`, `secret sec`, `config cfg`, `clusterconfig cc`, `gateway gw`, `region rgn` |
| Create imperatively | `create secret`, `create config`, `create credential`, `create namespace` (everything else via `apply`) |
| Update imperatively | `update session --approve\|--reject\|--expire-in`, `update credential --enable\|--disable\|--expire-in\|--max-authn\|--policy`, `update device\|authenticator --approve\|--reject`, `update secret\|config` |
| Delete | `octeliumctl delete <kind> <name>` (aliases `del`, `rm`); Services as `name` or `name.namespace` |

`apply` manages Config, Policy, IdentityProvider, Namespace, Group, User, Service, Credential
(Secret only with `--include-secret`) and ClusterConfig. Sessions, Devices, Authenticators,
Gateways and Regions are not applied.

## References

Read only what the task needs:

| Need | File |
| --- | --- |
| Apply semantics, repo layout, export-edit-apply, prune safety, the helper scripts | [references/apply-workflow.md](references/apply-workflow.md) |
| Kinds, naming (`svc.ns`), built-in resources, JSON Schema URLs | [references/resource-model.md](references/resource-model.md) |
| Policy evaluation, conditions, `ctx` fields, priorities, recipes, diagnosing denials | [references/policies.md](references/policies.md) |
| Service modes, upstreams, secretless auth, public/anonymous, TLS, containers, dynamic config | [references/services.md](references/services.md) |
| Users, Groups, IdentityProviders, Credentials, Sessions, Devices, first-admin bootstrap | [references/identity-and-access.md](references/identity-and-access.md) |
| Secrets, Configs and ClusterConfig | [references/secrets-and-cluster-config.md](references/secrets-and-cluster-config.md) |
| Access logs, observability, common errors | [references/troubleshooting.md](references/troubleshooting.md) |
| Exact `octeliumctl` flags (snapshot) | [references/cli-octeliumctl.md](references/cli-octeliumctl.md) |
| Starting-point YAML (validated) | `assets/templates/*.yaml` |

## Sources of truth

1. **Resource structure:** the JSON Schema for the kind,
   `https://octelium.com/schemas/octelium/latest/core.v1.<Kind>.schema.json` (bundled snapshot in
   `assets/schemas/`). Schema beats prose examples for field names, types and enums.
2. **CLI syntax:** `octeliumctl <command> --help` on the installed version beats the bundled
   snapshot.
3. **Semantics and newer features:** https://octelium.com/docs/octelium/latest/llms.txt and the
   page's Markdown twin (`<page-url>.md`). Check them when a feature isn't covered here or may
   have changed.
