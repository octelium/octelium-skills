# Current Cordium documentation

Start with the task below and read only the relevant pages. Links use the clean Markdown
representations; remove `.md` to open the canonical browser page. For discovery beyond this
map, use the [documentation index](https://octelium.com/docs/cordium/latest/llms.txt).
The current documentation takes precedence over older skill summaries and source notes.

## Overview, installation and access

| Need | Documentation |
| --- | --- |
| Product scope and use cases | [Introduction](https://octelium.com/docs/cordium/latest/overview/intro.md) |
| Resource relationships, full names and terminology | [Concepts](https://octelium.com/docs/cordium/latest/overview/concepts.md) |
| Isolation, components, lifecycle and storage | [How Cordium works](https://octelium.com/docs/cordium/latest/overview/how.md) |
| AI agent architecture and identity | [AI agents](https://octelium.com/docs/cordium/latest/overview/ai-agents.md) |
| New single-VM Cluster | [Quick installation](https://octelium.com/docs/cordium/latest/overview/quick-install.md) |
| Hands-on first Workspace and snapshot | [First steps](https://octelium.com/docs/cordium/latest/overview/first-steps.md) |
| Enable Cordium on an existing Octelium Cluster | [Cluster installation](https://octelium.com/docs/cordium/latest/install/cluster.md) |
| Install the client binary | [CLI installation](https://octelium.com/docs/cordium/latest/install/cli.md) |
| Choose between browser, CLI, SSH and SDKs | [Access methods](https://octelium.com/docs/cordium/latest/use/access-methods.md) |
| Workspace UI, settings and resource management | [Web portal](https://octelium.com/docs/cordium/latest/use/web-portal.md) |
| Exact commands, shared flags and output formats | [CLI reference](https://octelium.com/docs/cordium/latest/use/cli.md) |
| SSH, forwards, SFTP, VS Code and other IDEs | [SSH and IDEs](https://octelium.com/docs/cordium/latest/use/ssh.md) |
| Built-in chat agent, models, approvals and configuration | [Cordium Agent](https://octelium.com/docs/cordium/latest/use/agent.md) |
| Go, Python, Rust and TypeScript automation | [APIs and SDKs](https://octelium.com/docs/cordium/latest/use/api.md) |

## Workspace and Template configuration

| Need | Documentation |
| --- | --- |
| Spec structure, merging, variables and `.cordium.yaml` | [Configuration overview](https://octelium.com/docs/cordium/latest/workspaces/overview.md) |
| Registry images, Dockerfiles, repository builds and devcontainers | [Images and devcontainers](https://octelium.com/docs/cordium/latest/workspaces/image.md) |
| Branches, shallow clones, extra repositories and private git | [Repositories](https://octelium.com/docs/cordium/latest/workspaces/repositories.md) |
| Environment, task order, auto-stop, capabilities and nested containers | [Environment and tasks](https://octelium.com/docs/cordium/latest/workspaces/runtime.md) |
| Application URLs, listeners and sharing | [Applications and ports](https://octelium.com/docs/cordium/latest/workspaces/applications.md) |
| Default-deny egress, DNS and Gateway connectivity | [Network policies](https://octelium.com/docs/cordium/latest/workspaces/network.md) |
| Access or serve Octelium Services, Workspace identity and credential mapping | [Secretless access](https://octelium.com/docs/cordium/latest/workspaces/secretless.md) |
| Limit precedence, inactivity, timeouts and quotas | [Resources and timeouts](https://octelium.com/docs/cordium/latest/workspaces/resources.md) |
| Reusable blueprints and pre-build behavior | [Templates and pre-builds](https://octelium.com/docs/cordium/latest/workspaces/templates.md) |
| Persistent mounts, shared caches and resizing | [Volumes](https://octelium.com/docs/cordium/latest/workspaces/volumes.md) |
| Checkpoints, consistency, restore and forks | [Snapshots](https://octelium.com/docs/cordium/latest/workspaces/snapshots.md) |
| Personal and organization Spaces, Memberships and roles | [Spaces and Members](https://octelium.com/docs/cordium/latest/workspaces/spaces.md) |
| Space Secrets, private registries and OAuth2 git | [Secrets and GitProviders](https://octelium.com/docs/cordium/latest/workspaces/secrets.md) |
| Dotfiles, personal env vars, UserSecrets and SSH keys | [Personal configuration](https://octelium.com/docs/cordium/latest/workspaces/user-config.md) |

## Cluster management

| Need | Documentation |
| --- | --- |
| Whole-spec apply, ownership rules, defaults, storage selection and agent settings | [Cluster configuration](https://octelium.com/docs/cordium/latest/management/clusterconfig.md) |
| API, portal and administrator Policies; limiting Workspace Sessions | [Access control](https://octelium.com/docs/cordium/latest/management/access-control.md) |
| CSI backends, RWO/RWX, snapshot drivers, Regions and storage failures | [Storage](https://octelium.com/docs/cordium/latest/management/storage.md) |

## Worked examples

Choose a worked example when implementing a concrete workflow; use the configuration pages
above to change its fields. The [examples section](https://octelium.com/docs/cordium/latest/examples)
groups the following recipes.

| Task | Example |
| --- | --- |
| Run Claude Code against private git and a secretless LLM | [Claude Code](https://octelium.com/docs/cordium/latest/examples/ai/claude-code.md) |
| Configure a Codex sandbox and model provider | [Codex](https://octelium.com/docs/cordium/latest/examples/ai/codex.md) |
| Configure OpenCode providers | [OpenCode](https://octelium.com/docs/cordium/latest/examples/ai/opencode.md) |
| Fork a baseline for independent agent attempts | [Parallel agents](https://octelium.com/docs/cordium/latest/examples/ai/parallel-agents.md) |
| LLM gateways, per-run token budgets, model restrictions and audit | [Secretless LLM access](https://octelium.com/docs/cordium/latest/examples/ai/secretless-llm.md) |
| Build from a repository's devcontainer | [Dev containers](https://octelium.com/docs/cordium/latest/examples/dev/devcontainer.md) |
| Run frontend, API and database dependencies | [Full-stack development](https://octelium.com/docs/cordium/latest/examples/dev/fullstack.md) |
| Run databases and integration fixtures with Podman | [Running containers](https://octelium.com/docs/cordium/latest/examples/dev/containers.md) |
| Test and build with workload authentication | [CI/CD pipelines](https://octelium.com/docs/cordium/latest/examples/automation/cicd.md) |
| GitHub workflow, workload identity and cleanup | [GitHub Actions](https://octelium.com/docs/cordium/latest/examples/automation/github-actions.md) |
| Build and push container images | [Building container images](https://octelium.com/docs/cordium/latest/examples/automation/image-build.md) |
| Checkpoint, roll back into a new Workspace or fork a test baseline | [Checkpoints and forks](https://octelium.com/docs/cordium/latest/examples/workflows/snapshots.md) |
| Share datasets, caches and artifacts | [Sharing data with Volumes](https://octelium.com/docs/cordium/latest/examples/workflows/volumes.md) |
| Move setup work into pre-builds and refresh them | [Fast startup with pre-builds](https://octelium.com/docs/cordium/latest/examples/workflows/prebuilds.md) |
| Copy artifacts, use SSH and work across Workspaces | [Working across Workspaces](https://octelium.com/docs/cordium/latest/examples/workflows/ssh-cp.md) |
| Default-deny sandboxes and scoped identity for untrusted workloads | [Running untrusted code](https://octelium.com/docs/cordium/latest/examples/security/untrusted-code.md) |
| Databases, Kubernetes, HTTP and SSH without local credentials | [Accessing Octelium Services](https://octelium.com/docs/cordium/latest/examples/security/octelium.md) |
| Serve a preview, webhook or internal tool as an Octelium Service | [Serving Services from Workspaces](https://octelium.com/docs/cordium/latest/examples/security/serving.md) |

## Exact resource fields

Use the latest [Workspace schema](https://octelium.com/schemas/cordium/latest/cordium.v1.Workspace.schema.json),
[Template schema](https://octelium.com/schemas/cordium/latest/cordium.v1.Template.schema.json) or
[ClusterConfig schema](https://octelium.com/schemas/cordium/latest/cordium.v1.ClusterConfig.schema.json).
Other kinds use the same URL pattern. Bundled schemas are an offline snapshot; they do not
check whether a referenced resource exists or whether the caller is authorized.
