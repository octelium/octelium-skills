---
name: cordium
description: >-
  Install, configure and use Cordium, the identity-based sandbox platform built on Octelium and
  Kubernetes, with the `cordium` CLI. Covers installing Cordium (quick installer `--cordium`,
  `octops install-package`), running Workspaces (sandboxes) for developers, AI agents and CI
  (`cordium run`, `create workspace`, `exec`, `ssh`, `cp`, `logs`, ephemeral and
  auto-stop runs), Workspace and Template YAML (images, Dockerfiles, devcontainers, repositories,
  tasks, env vars, vars, limits, applications, egress rules), Spaces, Memberships, Templates and
  pre-builds, Secrets, GitProviders, UserSecrets, UserConfig, Volumes, WorkspaceSnapshots, the
  Cordium ClusterConfig (`cordium man`) and Policies granting Cordium access. Use whenever
  Cordium, its Workspaces or `cordium` commands are involved. Not for Octelium Services and
  Policies in general (octelium-management), client tunnels (octelium-connect), or installing
  and operating the Octelium Cluster (octelium-quick-install, octelium-kubernetes-install,
  octelium-cluster-ops).
license: Apache-2.0
compatibility: Requires the cordium CLI and an Octelium Session (octelium login) on a Cluster with the Cordium package. The helper script needs Python 3.9+ with PyYAML and jsonschema (or uv).
metadata:
  author: Octelium Labs, LLC
  version: "0.1.0"
  verified-against: cordium v0.15.0
  source-checked: cordium cc4af4b (2026-10-04)
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
  and CI, Workspace/Template YAML, Spaces, Memberships, Templates, pre-builds, Secrets,
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
   `cordium man get cc -o yaml`, edit only what was asked, keep `spec.space.ownership` (without
   it nobody can create a Space, including each User's automatic `default` Space).
7. **Keep secrets out of arguments, files and chat.** Have the user run
   `cordium create secret <name>.<space>` (prompt), or use `--from-env VAR` or `-f -`. A Secret
   used as an env var is plaintext to every process in the Workspace, including an agent;
   prefer a secretless Octelium Service for credentials an agent must not hold.
8. **A Workspace acts as its owner.** Its Session carries the owner's Octelium access. Run
   untrusted agents under a narrowly authorized User, restrict egress, and scope Policies with
   the Session's Cordium info (references/access-control.md). Never widen Policies, add
   capabilities or share ports to make something work unless the user asks for that change.
9. **Don't block on interactive commands.** `cordium run` and `cordium terminal` attach an
   interactive terminal. As an agent, use `cordium create ws ... -o json`, `cordium start`, poll
   `cordium get ws <name>`, then `cordium exec <name> --no-stdin -- <cmd>` with a timeout
   (references/workspaces.md). Without `--no-stdin`, a closed stdin kills the remote command.

In helper commands, `cordium_skill_dir` is the absolute directory containing this loaded
`SKILL.md`; keep the user's project as the working directory, e.g.
`uv run "$cordium_skill_dir/scripts/validate_resources.py" workspace.yaml`.

## Workflow

1. **Context.** Domain (`OCTELIUM_DOMAIN` or `--domain`), `cordium version` and
   `octelium version`, an existing Session (`octelium status`, bounded by a timeout), whether
   Cordium is installed (`cordium get spaces`). Missing CLI:
   `curl -fsSL https://octelium.com/install-cordium.sh | bash` (references/install.md).
2. **Route** with the references table below, and read the one the task needs.
3. **Prepare** the YAML or commands; validate files with the helper; check that referenced
   Secrets, Templates, GitProviders and Volumes exist in the same Space.
4. **Execute** and follow state: `cordium get ws <name>` until `RUNNING` (or `STOPPED` with
   `status.failure`), `cordium logs <name>` for image, clone and task output.
5. **Verify and report:** what was created or changed, how to reach it (terminal, SSH,
   application URL), what keeps running, and how to stop or delete it.

## Command map

| Task | Command |
| --- | --- |
| Create and attach a terminal | `cordium run [--file F] [--template T] [--image I \| --dockerfile D] [--repository URL] [--ephemeral] [--rm]`; `cordium run <ws>` attaches (starts if stopped) |
| Create without attaching | `cordium create ws [same flags] [--start] [--auto-stop] [--serve-all \| --serve S] [-o yaml]` |
| Lifecycle | `cordium start <ws> [--var K=V]`, `cordium stop <ws>`, `cordium delete ws <ws>` |
| Inside a running Workspace | `cordium exec <ws> [-w DIR] [-e K=V] [--root] [--no-stdin] -- CMD`, `cordium terminal <ws>`, `cordium logs <ws> [-t]` |
| SSH and files (need `octelium connect`) | `cordium ssh <ws> [-L ...] [-D ...] [-N] [-- CMD]`, `cordium ssh <ws> --print-config`, `cordium cp [-r] SRC DST` |
| Read | `cordium get ws\|spc\|tmpl\|sec\|gp\|usec\|vol\|snap [name] [-o yaml\|json]`, `--space S` for Space-scoped lists |
| Spaces and Templates | `cordium create space <space>`, `cordium create template <name>.<space> [-f F] [flags]`, `cordium build <tmpl> [--cancel]` |
| Secrets | `cordium create secret <name>.<space>` (prompt), `--from-env VAR`, `-f FILE\|-`; `cordium create usersecret <name>` |
| GitProviders | `cordium create gitprovider <name>.<space> --type github\|gitlab\|oauth2 --client-id ID --client-secret-from-secret <full Secret name>` |
| Storage (newer than v0.15.0) | `cordium create volume <name>[.<space>] --size MB [--shared]`, `cordium create snapshot <name> --workspace <ws>`, `create ws --volume NAME:PATH[:ro] \| --snapshot NAME` |
| Cluster settings (admins) | `cordium man get cc -o yaml`, `cordium man apply <file>` |
| Delete | `cordium delete ws\|tmpl\|sec\|gp\|usec\|vol\|snap <name>` (aliases `del`, `rm`) |

## References

Read only what the task needs:

| Need | File |
| --- | --- |
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
| Exact `cordium` flags (v0.15.0 snapshot) | [references/cli-cordium.md](references/cli-cordium.md) |
| Starting-point YAML (validated) | `assets/templates/*.yaml` |

## Sources of truth

1. **Resource structure:** the JSON Schema for the kind,
   `https://octelium.com/schemas/cordium/latest/cordium.v1.<Kind>.schema.json` (bundled snapshot
   in `assets/schemas/`). Schema beats prose examples for field names, types and enums.
2. **CLI syntax:** `cordium <command> --help` on the installed version beats the bundled
   snapshot.
3. **Behavior:** this skill was checked against the Cordium source; where the docs at
   https://octelium.com/docs/cordium/latest/llms.txt (Markdown twin at `<page-url>.md`) disagree
   with it, trust this skill and the installed version's behavior. Use the docs for features
   newer than this skill.
