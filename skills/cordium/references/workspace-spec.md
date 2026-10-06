# Workspace and Template YAML

Docs: https://octelium.com/docs/cordium/latest/use/config.md
Schemas: https://octelium.com/schemas/cordium/latest/cordium.v1.Workspace.schema.json,
https://octelium.com/schemas/cordium/latest/cordium.v1.Template.schema.json

## Files and validation

| File | Read by | Used |
| --- | --- | --- |
| Workspace document | `cordium run --file`, `cordium create ws --file` | `spec` only; name and status are assigned by the Cluster |
| Template document | `cordium create template <name>.<space> -f` | `spec` only; the name comes from the argument |
| Repository config: first of `.cordium/workspace.yaml`, `.cordium/workspace.yml`, `.cordium.yaml`, `.cordium.yml` in the primary repository | The Workspace while initializing | Its `spec` is merged over the Template and Workspace specs |

Both CLIs parse YAML leniently: unknown or misspelled fields are dropped without a message, and
an invalid repository config file is ignored. Include `kind` and validate before use:

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
| Spec | Template spec, then the Workspace spec, then the repository config file. A field set at a later level wins; lists (`envVars`, `tasks`, `additionalRepositories`, `applications`, egress `rules`, capabilities) are concatenated. |
| Environment | UserConfig, then Space `runtime.envVars`, then the merged spec; later wins for the same key. Cordium's own variables (`CORDIUM_NAME`, `OCTELIUM_*`, `SSH_AUTH_SOCK`) are set last. |
| Tasks | Merged spec tasks, then UserConfig tasks, then Space tasks; within that order all `ON_CREATE` (fresh runs only), then all `POST_START`; `PRE_STOP` on stop. |
| Variables | Template `vars`, then Workspace `vars`, then `cordium start --var` (that run only). |
| Limits | The Workspace `limit` replaces the Template `limit` when set; each missing dimension falls back to the ClusterConfig default for the Space type, then 2000 millicores, 6000 MB memory, 20000 MB storage; the Space `maxLimit` and ClusterConfig `maxLimit` then cap them. In the source checked, a Space `limit.defaultLimit` is not applied to Workspaces created from a Template (all of them). |
| Capabilities | Adds and drops from the merged spec, the Space runtime and the ClusterConfig are all passed to the container. |
| Egress | From the merged spec: a Workspace can replace a Template's `defaultAction`, while Template DENY rules still apply. |

`runtime.timeout` is read from the Workspace's own spec, not from the Template.

## Variables

`${{ vars.NAME }}` (or `${{vars.NAME}}`) is substituted after merging, in: `image.registry.url`,
`image.dockerfile.url`, `image.git.url/dockerfile/context`, repository URLs (primary and
additional), `runtime.envVars[].value`, and tasks' `run`, `workingDir` and `envVars[].value`. It
is not substituted in inline Dockerfiles, `fromSecret`, applications, limits, or Space and
UserConfig tasks. A reference to an undefined variable is replaced with an empty string. `vars`
entries have only `name` and `value`.

The API validates specs before substitution (v0.15.0 and later): a variable in
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
  url: https://github.com/myorg/api        # https only
  cloneOptions:
    branch: main
    checkout: v1.4.0                       # tag or commit after cloning
    singleBranch: true
    shallowSubmodules: true
    disableLazyUnshallow: true             # default: shallow clone, full history fetched in the background
    depth: 1                               # only effective with disableLazyUnshallow
  authentication:
    http:
      username: oauth2
      password:
        fromSecret: github-pat.my-project.alice
additionalRepositories:
  - name: shared                           # cloned to /workspace/additional-repos/shared
    repository:
      url: https://github.com/myorg/shared
```

The primary repository is cloned to `/workspace/repo`. `additionalRepositories[].clonePath` is
ignored in the source checked: they land in `/workspace/additional-repos/<name>`, and a failed
additional clone is logged without stopping the run. With a GitProvider on the Template, omit
`authentication`: the User's OAuth2 token is injected (references/spaces-and-templates.md).

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

Egress rules filter the Workspace's direct traffic: DENY rules win over ALLOW rules, unmatched
traffic follows `defaultAction`, and `ALLOW_PUBLIC` drops private and reserved ranges (RFC 1918,
`100.64.0.0/10`, ...). Loopback, link-local and the Cluster's own networks are always denied.
Access to Octelium Services goes through the Workspace's tunnel and is decided by Policies, not
by these rules. With `defaultAction: DENY`, allow everything the job needs, including the DNS
resolver in the Workspace's `/etc/resolv.conf`, and test the result
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

## Applications, limits, lifetime

```yaml fragment
applications:                 # Workspace only
  - name: web                 # https://<ws>.cordium.<DOMAIN> (default) or web_<ws>...
    port: 3000
    isDefault: true           # at most one
  - name: api
    port: 8080
limit:
  cpu: {millicores: 4000}
  memory: {megabytes: 8192}
  storage: {megabytes: 30000}
isEphemeral: true             # Workspace only; the CLI replaces it with --ephemeral (false if omitted)
```

## Example: one-shot agent run

```yaml cordium
kind: Workspace
spec:
  image:
    registry:
      url: node:22-bookworm
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
  limit:
    cpu:
      millicores: 2000
    memory:
      megabytes: 4096
```

Replace `anthropic-key.agents.alice` with the real full Secret name. Run it with
`cordium create ws --file agent.yaml --ephemeral --branch <branch> -o json`, then
`cordium start <ws> --var TASK="..."`, and follow `cordium logs <ws>`. More starting points:
`assets/templates/`.
