---
name: cordium
description: >-
  Install, configure and use Cordium, the identity-based sandbox platform built on Octelium
  and Kubernetes. Use for Cordium Workspaces, the cordium CLI, Go/Python/Rust/TypeScript SDKs,
  the web portal and Cordium Agent, Workspace/Template YAML, Spaces and Memberships, pre-builds,
  Secrets and GitProviders, UserConfig and UserSecrets, Volumes and WorkspaceSnapshots,
  secretless access, egress rules and the Cordium ClusterConfig. Routes to configuration
  references and worked examples for development, AI agents and CI/CD. Not for Octelium
  Services and Policies in general (octelium-management), client tunnels (octelium-connect),
  or installing and operating the Octelium Cluster (octelium-quick-install,
  octelium-kubernetes-install, octelium-cluster-ops).
license: Apache-2.0
compatibility: Cordium operations require an Octelium Session on a Cluster with the Cordium package; use the cordium CLI, portal or SDKs. The YAML helper needs Python 3.9+ with PyYAML and jsonschema (or uv).
metadata:
  author: Octelium Labs, LLC
  version: "0.1.0"
  verified-against: Cordium latest documentation (2026-10-09)
---

# Cordium: sandboxes on Octelium

Cordium is a package installed on an Octelium Cluster. A _Workspace_ (synonymous with sandbox)
is a rootless, container-based environment running on Kubernetes nodes labeled
`octelium.com/node-mode-cordium`. Every Workspace run gets its own Octelium Session of its owner,
and an `octelium connect` process inside it, so code in the Workspace reaches the Octelium
_Services_ its owner is allowed to reach without holding their credentials ("secretless").
Workspaces live in _Spaces_ and are created from _Templates_. The `cordium` CLI, the web console
at `https://cordium.<DOMAIN>`, SSH and the gRPC API all use the same Cordium API.

## Scope

- **Use for:** installing or enabling Cordium, running Workspaces interactively or for agents
  and CI, SDK automation, the portal's Cordium Agent, Workspace/Template YAML, Spaces,
  Memberships, Templates, pre-builds, Secrets,
  GitProviders, UserSecrets, UserConfig, Volumes, WorkspaceSnapshots, the Cordium ClusterConfig,
  Policies for Cordium access, Cordium troubleshooting.
- **Hand off:** the Octelium Services a Workspace should reach, and Policies beyond Cordium
  access → **octelium-management**. `octelium login`/`connect` problems on a laptop →
  **octelium-connect**. No Octelium Cluster yet → **octelium-quick-install** (single VM) or
  **octelium-kubernetes-install**. Octelium upgrades, Cluster TLS and health →
  **octelium-cluster-ops**.

## Ground rules

Follow these while preserving the user's authorized target and outcome. Prepare the concrete
change first; ask only for missing inputs or unresolved destructive scope.

1. **One login for all CLIs.** There is no `cordium login`: `cordium` uses the Octelium Session
   of `octelium login`. Never start a browser login unannounced; guard the first call with the
   agent's command timeout. Inside a Workspace, `OCTELIUM_AUTH_PROXY_SOCKET` is set and the CLIs
   are already authenticated as the Workspace: don't run `login`/`logout` there.
2. **Look before you change.** `cordium get <kind> <name> -o yaml` for everything you touch.
   Workspace names are generated (3 to 6 characters); read them, never guess.
3. **Validate YAML first.** `cordium run/create --file` and `create template -f` silently drop
   unknown fields; `cordium man apply` only warns. Run `scripts/validate_resources.py` on every
   Workspace, Template and ClusterConfig file before using it (references/workspace-spec.md).
4. **Use full names in references.** Spaces are `<space>.<owner>` (personal) or
   `<space>.cordium` (organization); Secrets, Templates, GitProviders and Volumes are
   `<name>.<space>.<owner>`. Commands expand short names, but `fromSecret`, `gitProvider` and
   `--env-from-secret` values must be the full name (references/resource-model.md).
5. **Deletes are immediate.** `cordium delete ...`, `run --rm`, stopping an ephemeral
   Workspace (storage discarded) and deleting a Space (all its Workspaces and their Sessions,
   Templates, Secrets, Volumes, WorkspaceSnapshots, GitProviders, Memberships) have no prompt
   or undo. State what is lost and proceed only within the user's authorized scope.
6. **`cordium man apply` replaces the whole ClusterConfig spec.** Export it with
   `cordium man get cc -o yaml`, edit only what was asked, and preserve `spec.space.ownership`.
   Without ownership rules, Users cannot create additional Spaces; their automatic `default`
   Space is still created.
7. **Keep secrets out of arguments, files and chat.** Have the user run
   `cordium create secret <name>.<space>` (prompt), or use `--from-env VAR` or `-f -`. A Secret
   used as an env var is plaintext to every process in the Workspace, including an agent;
   prefer a secretless Octelium Service for credentials an agent must not hold.
8. **A Workspace acts as its owner.** Its Session carries the owner's Octelium access. Run
   agents with the access their task needs and scope Policies with the Session's Cordium info
   (references/access-control.md). Egress restrictions must allow DNS and the Cluster Gateway
   addresses for secretless access. Keep provider credentials at Octelium proxies when possible.
9. **Don't block on interactive commands.** `cordium run` and `cordium terminal` attach an
   interactive terminal. As an agent, use `cordium create ws ... -o json`, `cordium start`, poll
   `cordium get ws <name>`, then `cordium exec <name> --no-stdin -- <cmd>` with a timeout
   (references/workspaces.md). Without `--no-stdin`, a closed stdin kills the remote command.
   For tasks using Octelium Services, use `POST_START` and wait for connectivity. Auto-stop
   jobs can finish before reaching `RUNNING`; inspect their failure and stopping reason.

In helper commands, `cordium_skill_dir` is the absolute directory containing this loaded
`SKILL.md`; keep the user's project as the working directory, e.g.
`uv run "$cordium_skill_dir/scripts/validate_resources.py" workspace.yaml`.

## Workflow

1. **Route** with the references table below. Use [references/documentation-map.md](references/documentation-map.md)
   to find the current documentation and a worked example for the task.
2. **Context for execution.** Domain (`OCTELIUM_DOMAIN` or `--domain`), the installed CLI or
   SDK version, an existing Session (`octelium status`, bounded by a timeout), and whether
   Cordium is installed (`cordium get spaces`). For a missing CLI, see references/install.md.
   Documentation questions and YAML authoring do not need a live Cluster connection.
3. **Prepare** the YAML or commands; validate files with the helper; check that referenced
   Secrets, Templates, GitProviders and Volumes exist in the same Space.
4. **Execute** and follow state with a deadline: wait for `RUNNING` before executing commands,
   or `STOPPED` for auto-stop jobs. Inspect `status.failure` and `status.stoppingReason`;
   stream `cordium logs <name>` for image, clone and task output while the Workspace runs.
5. **Verify and report:** what was created or changed, how to reach it (terminal, SSH,
   application URL), what keeps running, and how to stop or delete it.

## Command map

| Task | Command |
| --- | --- |
| Create and attach a terminal | `cordium run [--file F] [--template T] [--image I \| --dockerfile D] [--repository URL] [--ephemeral] [--rm]`; `cordium run <ws>` attaches (starts if stopped) |
| Create without attaching | `cordium create ws [same flags] [--start] [--auto-stop] [--serve-all \| --serve S] [-o yaml]` |
| Lifecycle | `cordium start <ws> [--var K=V]`, `cordium stop <ws>`, `cordium delete ws <ws>` |
| Inside a running Workspace | `cordium exec <ws> [-w DIR] [-e K=V] [--root] [--no-stdin] -- CMD`, `cordium terminal <ws>`, `cordium logs <ws> [-t]` |
| SSH, files and IDEs (need `octelium connect`) | `cordium ssh <ws> [-L ...] [-D ...] [-N] [-- CMD]`, `cordium ssh <ws> --print-config`, `cordium cp [-r] SRC DST`, `cordium code <ws> [--dir DIR]` |
| Read | `cordium get ws\|spc\|tmpl\|sec\|gp\|usec\|vol\|snap [name] [-o yaml\|json]`, `--space S` for Space-scoped lists |
| Spaces and Templates | `cordium create space <space>`, `cordium create template <name>.<space> [-f F] [flags]`, `cordium build <tmpl> [--cancel]` |
| Secrets | `cordium create secret <name>.<space>` (prompt), `--from-env VAR`, `-f FILE\|-`; `cordium create usersecret <name>` |
| GitProviders | `cordium create gitprovider <name>.<space> --type github\|gitlab\|oauth2 --client-id ID --client-secret-from-secret <full Secret name>` |
| Storage | `cordium create volume <name>[.<space>] --size MB [--shared] [--region R]`, `cordium create snapshot <name> --workspace <ws>`, `create ws --volume NAME:PATH[:ro] \| --snapshot NAME` |
| Cluster settings (admins) | `cordium man get cc -o yaml`, `cordium man apply <file>` |
| Delete | `cordium delete ws\|tmpl\|sec\|gp\|usec\|vol\|snap <name>` (aliases `del`, `rm`) |

## References

Read only what the task needs:

| Need | File |
| --- | --- |
| Current documentation by task, configuration topic and worked example | [references/documentation-map.md](references/documentation-map.md) |
| Installing Cordium, nodes, storage, DNS/TLS for `*.cordium.<DOMAIN>`, upgrades, CLI install | [references/install.md](references/install.md) |
| Authentication, Policies for the Cordium API and console, Space roles, Workspace identity, scoping agents | [references/access-control.md](references/access-control.md) |
| Kinds, naming and full-name rules, quotas and defaults, JSON Schema URLs | [references/resource-model.md](references/resource-model.md) |
| Running Workspaces: lifecycle, agent and CI patterns, exec/ssh/cp, applications, inside a Workspace | [references/workspaces.md](references/workspaces.md) |
| Workspace and Template YAML: every field, merging, variables, tasks, repo config files, validation | [references/workspace-spec.md](references/workspace-spec.md) |
| Spaces, Memberships, Templates, pre-builds, GitProviders | [references/spaces-and-templates.md](references/spaces-and-templates.md) |
| Secrets, UserSecrets, UserConfig and dotfiles | [references/secrets-and-user-config.md](references/secrets-and-user-config.md) |
| Volumes, WorkspaceSnapshots, storage and snapshot classes | [references/storage.md](references/storage.md) |
| Cordium ClusterConfig: ownership, limits, timeouts, storage rules | [references/cluster-config.md](references/cluster-config.md) |
| Error messages, failure types, Kubernetes-level checks | [references/troubleshooting.md](references/troubleshooting.md) |
| Current CLI workflow, flags and direct links to command sections | [references/cli-workflows.md](references/cli-workflows.md) |
| SDK selection, readiness, cleanup and the built-in Cordium Agent | [references/api-and-agent.md](references/api-and-agent.md) |
| Offline help for an installed v0.15.0 CLI only; lacks newer commands | [references/cli-cordium.md](references/cli-cordium.md) |
| Development server, CI, secretless agent, devcontainer and ClusterConfig YAML | [references/workspace-spec.md](references/workspace-spec.md#starting-point-assets) |

## Sources of truth

1. **Behavior and workflows:** the [current Cordium documentation](https://octelium.com/docs/cordium/latest/llms.txt).
   When it disagrees with this skill's summaries or older source notes, prefer the current docs.
   Read only the relevant pages through [the documentation map](references/documentation-map.md).
   Canonical pages have a Markdown twin at `<page-url>.md`; use `.md#section` for an anchor.
2. **Resource structure:** the latest JSON Schema for the kind,
   `https://octelium.com/schemas/cordium/latest/cordium.v1.<Kind>.schema.json` (offline snapshot
   in `assets/schemas/`). Use it for exact field names, types and enums.
3. **Installed-version syntax:** `cordium <command> --help`. The bundled v0.15.0 help is a
   historical fallback, not a reference for current features. If a documented feature is
   unavailable on the installed CLI or Cluster, identify the version mismatch before using it.
4. **Unresolved details:** consult [Cordium source](https://github.com/octelium/cordium) for
   the relevant version. Do not turn an old implementation bug into current guidance.
