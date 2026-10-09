# Workspace and Template YAML

Docs: [Configuration overview](https://octelium.com/docs/cordium/latest/workspaces/overview.md).
For field-specific guidance, use [images](https://octelium.com/docs/cordium/latest/workspaces/image.md),
[repositories](https://octelium.com/docs/cordium/latest/workspaces/repositories.md),
[environment and tasks](https://octelium.com/docs/cordium/latest/workspaces/runtime.md),
[applications](https://octelium.com/docs/cordium/latest/workspaces/applications.md),
[network policies](https://octelium.com/docs/cordium/latest/workspaces/network.md) and
[resources and timeouts](https://octelium.com/docs/cordium/latest/workspaces/resources.md).
Schemas: https://octelium.com/schemas/cordium/latest/cordium.v1.Workspace.schema.json,
https://octelium.com/schemas/cordium/latest/cordium.v1.Template.schema.json

## Files and validation

| File | Read by | Used |
| --- | --- | --- |
| Workspace document | `cordium run --file`, `cordium create ws --file` | `spec` only; name and status are assigned by the Cluster |
| Template document | `cordium create template <name>.<space> -f` | `spec` only; the name comes from the argument |
| Repository config: first of `.cordium/workspace.yaml`, `.cordium/workspace.yml`, `.cordium.yaml`, `.cordium.yml` in the primary repository | The Workspace while initializing | Its `spec` is merged over the Template and Workspace specs |

Both CLIs parse YAML leniently: unknown or misspelled fields are dropped without a message.
Repository configuration is validated like any other spec, including its Secret references.
Include `kind` in CLI files and validate before use:

```bash
uv run "$cordium_skill_dir/scripts/validate_resources.py" workspace.yaml template.yaml
uv run "$cordium_skill_dir/scripts/validate_resources.py" --kind Workspace .cordium.yaml
```

The helper checks the JSON Schema (unknown fields, enums, one-of choices) and the API's own
limits, and warns about short Secret references, undefined variables, ignored fields and risky
settings. Exit status 0 means no errors; review every warning.

A Template spec has `image`, `runtime`, `repository`, `additionalRepositories`, `limit`, `vars`
and `gitProvider`. A Workspace spec adds `applications` and `isEphemeral` and has no
`gitProvider`.

## How levels combine

| What | Rule |
| --- | --- |
| Spec | Template spec, then Workspace spec, then repository configuration. Nested objects merge field by field; lists (env vars, tasks, additional repositories, Volume mounts, egress rules, capabilities) concatenate in that order. Applications and ephemerality belong to the Workspace; GitProvider belongs to the Template. |
| Environment | UserConfig, then Space `runtime.envVars`, then the merged spec; later wins for the same key. Cordium's own variables (`CORDIUM_NAME`, `OCTELIUM_*`, `SSH_AUTH_SOCK`) are set last. |
| Tasks | Template, Workspace, repository configuration, UserConfig, then Space tasks within each type: `ON_CREATE` (fresh runs), `POST_START` (every start), `PRE_STOP` (on stop). |
| Variables | Template `vars`, then Workspace `vars`, then `cordium start --var` (that run only). |
| Limits | First whole `limit` set by Workspace, Template, or ORGANIZATION Space `defaultLimit`; missing dimensions use ClusterConfig defaults for the Space type, then 2000 millicores, 6000 MB memory, 20000 MB storage. Space and ClusterConfig `maxLimit` cap the result. Read `status.limit` for effective values. |
| Capabilities | Adds and drops from the merged spec, the Space runtime and the ClusterConfig are all passed to the container. |
| Egress | From the merged spec: a Workspace can replace a Template's `defaultAction`, while Template DENY rules still apply. |

Repository applications are not read. Its image is used only when neither the Workspace nor
Template sets an image, or when the image is explicitly built from the repository.

## Variables

`${{ vars.NAME }}` (or `${{vars.NAME}}`) is substituted after merging, in: `image.registry.url`,
`image.dockerfile.url`, `image.git.url/dockerfile/context`, repository URLs (primary and
additional), `runtime.envVars[].value`, and tasks' `run`, `workingDir` and `envVars[].value`. It
is not substituted in inline Dockerfiles, `fromSecret`, applications, limits, or Space and
UserConfig tasks. A reference to an undefined variable is replaced with an empty string. `vars`
entries have only `name` and `value`.

The API validates specs before substitution: a variable in
`cloneOptions.branch`, `cloneOptions.checkout` or `image.git.checkout` is rejected
(`Invalid git branch: ...`), and so is a repository URL that is only a variable or contains a
spaced reference (`Invalid repository URL`). Inside a URL, write the reference without spaces
(`https://github.com/${{vars.ORG}}/api`). Choose a branch per Workspace with `--branch`, or per
run with a task such as `git -C /workspace/repo checkout "${{ vars.BRANCH }}"`.

## Image

Exactly one source:

| Field | Meaning |
| --- | --- |
| `image.registry.url` | Image reference, e.g. `python:3.12-bookworm`; `authentication.username` and `authentication.password.fromSecret` for private registries |
| `image.dockerfile.inline` / `.url` | Dockerfile text (max 5000 characters, no build context) or a URL to download it from |
| `image.git.url`, `checkout`, `dockerfile`, `context` | Build from a separate repository; without `dockerfile`, its devcontainer spec is used |
| `image.repository.devcontainer.dirPath` / `.dockerfile.path`, `.context` | Build from the Workspace's primary repository |

Without `image`, a Workspace with a primary repository uses, in order: the repository config
file's `image`, `.devcontainer/devcontainer.json` or `.devcontainer.json` in the repository,
else the Cordium base image. Devcontainer support covers `image`/`build`/Docker Compose service,
`containerEnv`, features and lifecycle commands. Images are pulled or built only on fresh runs
and pre-builds.

## Repositories

```yaml fragment
repository:
  url: https://github.com/myorg/api
  cloneOptions:
    branch: main
    checkout: v1.4.0
    singleBranch: true
    shallowSubmodules: true
    disableLazyUnshallow: true
    depth: 1
  authentication:
    http:
      username: oauth2
      password:
        fromSecret: github-pat.my-project.alice
additionalRepositories:
  - name: shared
    repository:
      url: https://github.com/myorg/shared
```

The primary repository is cloned to `/workspace/repo`; additional repositories land in
`/workspace/additional-repos/<name>`. Clones happen on fresh runs only. By default, shallow
clones are unshallowed asynchronously; `depth` takes effect with `disableLazyUnshallow: true`.
With a GitProvider on the Template, omit `authentication` and sign in from the stopped
Workspace's portal page. Its git credential helper makes the token usable by processes in
the Workspace; prefer scoped read-only tokens or secretless git for untrusted workloads.

## Runtime

| Field | Notes |
| --- | --- |
| `envVars[]` | `key` (ASCII, max 64) and either `value` (1 to 1024 characters) or `fromSecret` (full Secret name); max 128 |
| `tasks[]` | See below; max 128 |
| `autoStop` | Stop after all non-background tasks finish |
| `cmd`, `entrypoint` | Override the image (max 1024 characters); the default command is `sleep infinity` |
| `disableInit` | Don't run Cordium's minimal init as PID 1 |
| `devcontainers.features[]` | `reference` (OCI) and `options[]` (`key`, `value`), merged with the repository's devcontainer features |
| `octelium.serveServices[]`, `octelium.serveAll` | Serve the owner's Octelium Services from inside the Workspace |
| `network.egress` | `defaultAction` (`ALLOW_PUBLIC` default, or `DENY`) and `rules[]` with `action` (`ALLOW`/`DENY`), `cidrs` (canonical, e.g. `10.0.0.0/8`) and optional `ports`; max 64 rules, 64 CIDRs and 64 ports per rule |
| `filesystem.readOnly` | Read-only root filesystem |
| `capabilities.add/drop` | Linux capability names such as `NET_ADMIN` (`^(ALL\|[A-Z][A-Z0-9_]{0,29})$`) |
| `timeout.mode` | `DEFAULT`, or `DISABLED` (honored only when ClusterConfig `workspace.timeout.allowNoTimeout` is true) |
| `volumeMounts[]` | `volumeRef.name` (a Volume of the same Space), absolute `mountPath`, `readOnly` (references/storage.md) |

Egress rules are enforced outside the sandbox. DENY rules win over ALLOW rules; unmatched
traffic follows `defaultAction`, and `ALLOW_PUBLIC` drops non-public ranges. Supervisor/pod
addresses, the pod gateway, external loopback and link-local destinations are always denied.
Explicit ALLOW rules may permit other private destinations. With `defaultAction: DENY`, allow
DNS (`8.8.8.8:53`), git hosts and package registries, plus the Cluster's public Gateway addresses
for `octelium connect`. Requests inside the tunnel are then governed by Octelium Policies.
Image pulls/builds happen before this policy is applied; clones and feature downloads happen
inside it. Test the result
(`cordium exec <ws> --no-stdin -- getent hosts example.com`) before relying on it.

```yaml fragment
network:
  egress:
    defaultAction: ALLOW_PUBLIC
    rules:
      - action: DENY
        cidrs: ["203.0.113.0/24"]
      - action: ALLOW
        cidrs: ["10.20.0.0/16"]
        ports: [5432]
```

### Tasks

| Field | Notes |
| --- | --- |
| `name` | Shown in logs and failures |
| `run` | Shell command, max 5000 characters |
| `type` | Required: `ON_CREATE` (fresh runs), `POST_START` (every start), `PRE_STOP` (before stopping) |
| `onFailure` | Only `ON_FAILURE_ABORT` stops initialization (failure type `task` with the exit code); unset or `ON_FAILURE_CONTINUE` logs and continues |
| `isBackground` | Start without waiting; skipped during pre-builds |
| `workingDir` | Defaults to the Workspace User's home |
| `runAsRoot` | Run as root instead of the Workspace User |
| `envVars[]` | `key`/`value` pairs for this task only |

`RUNNING` is reached after the non-background `ON_CREATE` and `POST_START` tasks finish, so a
long foreground task delays it; use `isBackground: true` for servers.

`octelium connect` is the first background `POST_START` task. Tasks accessing Octelium Services
must use `POST_START` and wait for the Service to become reachable. Foreground tasks have a
combined 60-minute timeout on fresh runs and 20 minutes on later persistent runs; `PRE_STOP`
has 10 minutes. Long jobs can run in the background and call `cordium stop` when finished;
do not combine that pattern with auto-stop, which does not wait for background tasks.

## Applications, limits, lifetime

```yaml fragment
applications:
  - name: web
    port: 3000
    isDefault: true
  - name: api
    port: 8080
limit:
  cpu: {millicores: 4000}
  memory: {megabytes: 8192}
  storage: {megabytes: 30000}
isEphemeral: true
```

## Example: one-shot agent run

```yaml cordium
kind: Workspace
spec:
  image:
    registry:
      url: node:24-bookworm
  repository:
    url: https://github.com/myorg/api-service
  vars:
    - name: TASK
      value: Fix the failing unit tests.
  runtime:
    autoStop: true
    envVars:
      - key: ANTHROPIC_API_KEY
        fromSecret: anthropic-key.agents.alice
    tasks:
      - name: install
        type: ON_CREATE
        workingDir: /workspace/repo
        run: npm ci && npm install -g @anthropic-ai/claude-code
        onFailure: ON_FAILURE_ABORT
      - name: agent
        type: POST_START
        workingDir: /workspace/repo
        run: claude -p "${{ vars.TASK }}"
        onFailure: ON_FAILURE_ABORT
  limit:
    cpu:
      millicores: 2000
    memory:
      megabytes: 4096
```

This example uses a Space Secret; its value is readable by the agent. Prefer the
[secretless Claude Code recipe](https://octelium.com/docs/cordium/latest/examples/ai/claude-code.md)
when an Octelium LLM Service is available. Replace `anthropic-key.agents.alice` with the real full Secret name. Run it with
`cordium create ws --file agent.yaml --ephemeral --branch <branch> -o json`, then
`cordium start <ws> --var TASK="..."`, and follow `cordium logs <ws>`. More starting points:
the assets below.

## Starting-point assets

Copy the relevant asset into the user's project, replace placeholders, and validate it before
creating a resource. Workspace and Template files contain `kind` for the helper; the CLI uses
their `spec`. Pass `--ephemeral` explicitly for disposable CLI-created Workspaces.

| Asset | Use | Prerequisites |
| --- | --- | --- |
| [workspace-dev.yaml](../assets/templates/workspace-dev.yaml) | Persistent Node.js dev server with an HTTPS application | Repository with `npm ci` and a `dev` script supporting `--host` |
| [workspace-ci.yaml](../assets/templates/workspace-ci.yaml) | Foreground test job with abort-on-failure and auto-stop | Choose the repository, image and test command; capture logs while running |
| [workspace-secretless-agent.yaml](../assets/templates/workspace-secretless-agent.yaml) | One-shot Claude Code run through an Octelium LLM Service | Authorized LLM Service; image with Node.js, npm, curl and timeout; task fits foreground timeout |
| [workspace-agent.yaml](../assets/templates/workspace-agent.yaml) | Agent with a Space Secret when direct credentials are needed | Create the Secret and use its full name; value is visible inside the Workspace |
| [template-devcontainer.yaml](../assets/templates/template-devcontainer.yaml) | Team devcontainer Template with GitProvider | Create GitProvider; each User signs in before starting; pre-builds need separate Secret-based git auth |
| [cluster-config.yaml](../assets/templates/cluster-config.yaml) | Ownership, quotas, limits and timeouts | Merge into exported current ClusterConfig; applying replaces the entire spec |
