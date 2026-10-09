# SDKs and the Cordium Agent

## APIs and SDKs

Read [APIs and SDKs](https://octelium.com/docs/cordium/latest/use/api.md) for maintained examples
of creating, starting, executing commands, transferring files and forking snapshots.
All clients use the same Octelium identity and server-side authorization as the CLI.

| Language | Package | Client | Timeouts |
| --- | --- | --- | --- |
| Go | `github.com/octelium/cordium/cordium-go` | `cordium.New(ctx)` | Context deadlines and `time.Duration` |
| Python | `cordium-sdk` | `Cordium`, `AsyncCordium` | Seconds |
| Rust | `cordium` crate | `Client::from_env().await` | `Duration` |
| TypeScript/JavaScript | `@octelium/cordium` | `new Cordium()` | Milliseconds; cancellation via `AbortSignal` |

- `Run`/`run()` creates, starts and waits for `RUNNING`; `Create`/`create()` leaves the
  Workspace stopped. Background tasks do not delay readiness, so health-check applications.
- A successful start does not imply a command succeeded: inspect the returned exit status,
  use Go's `result.Err()`, or use the other SDKs' `check` option.
- Command strings run through the Workspace shell. Use Go's `cordium.Argv`, Python argument
  lists, Rust's `Command::argv`, or TypeScript's `argv` for literal arguments.
- Use file helpers for text, bytes, uploads and downloads. They require POSIX tools such as
  `sh`, `base64` and `head` in the image. CLI SSH/SFTP transfers additionally need a tunnel.
- Delete disposable Workspaces in `finally`/`defer` cleanup. Closing a client releases its
  connections but does not stop or delete Workspaces. Stopping an ephemeral Workspace removes
  its storage but leaves the resource.
- Startup failures retain the Workspace for inspection. Go returns a handle with the error;
  Python and TypeScript expose `error.workspace`; Rust returns `Error::RunFailed` with a handle.
- Take a snapshot, wait for `STATE_READY`, then fork new Workspaces from it. Restores stay in
  the snapshot's Space and Region, skip fresh-run work and use current runtime configuration.
  Read [parallel agents](https://octelium.com/docs/cordium/latest/examples/ai/parallel-agents.md)
  and [checkpoints and forks](https://octelium.com/docs/cordium/latest/examples/workflows/snapshots.md).

For operations beyond the convenience API, use the generated `MainService`, `WorkspaceService`
and `ManagementService` clients exposed by each SDK. Exact resource fields come from the
latest schemas, not from convenience-option names. Authorization requirements are described in
[Access control](https://octelium.com/docs/cordium/latest/management/access-control.md).

## Built-in Cordium Agent

Read [Cordium Agent](https://octelium.com/docs/cordium/latest/use/agent.md) when configuring the
portal's chat agent. It is distinct from running Claude Code, Codex or OpenCode as a workload;
those recipes are in [the documentation map](documentation-map.md#worked-examples).

The portal's `/agent` page provisions a personal system Space `octelium.<USER>`, a
`cordium-agent` Template and a persistent Workspace running `@octelium/cordium-agent`. The
agent uses its owner's identity through the authentication proxy; conversations, uploads,
settings and artifacts live in its Workspace. Do not share the agent's application with other
Users, since they would act with its owner's permissions.

Cluster administrators configure `ClusterConfig.spec.agent`. Export the current configuration
first and merge the change, because `cordium man apply` replaces the whole spec.

| Field | Purpose |
| --- | --- |
| `isDisabled` | Disable the agent; existing agent Workspaces remain |
| `llm.service`, `llm.model` | Default Octelium LLM Service and model; authorize the Users for that Service |
| `version`, `image`, `limit` | Agent npm version/dist-tag, Workspace image and resources |
| `config` | Additional agent settings merged over generated configuration |
| `config.llm.api` | Provider protocol, such as `anthropic-messages` or `openai-responses` |
| `config.llm.loginProviders` | Allowed subscription providers; `[]` requires the configured LLM Service |
| `config.approvals.api` | `destructive` (default), `write` or `never` |
| `config.approvals.commands` | Require approval for shell commands |
| `config.skills.repositories` | Additional skills repositories |

The default approval mode covers destructive and sensitive API calls. Approvals supplement
server-side Policies; they do not grant additional access. Users may also select their own
Claude or ChatGPT subscription from the agent page when subscription login is enabled.

For an agent in a custom Workspace, use the
[custom Workspace example](https://octelium.com/docs/cordium/latest/use/agent.md#running-the-agent-in-your-own-workspaces).
It needs Node.js 22.19+ and git, runs `npx @octelium/cordium-agent ... serve` as a background
`POST_START` task, and serves port 8080 as its default application. Diagnose it with
`npx @octelium/cordium-agent doctor`. Its [HTTP/JSON and SSE API](https://octelium.com/docs/cordium/latest/use/agent.md#http-api)
provides conversations, runs, approvals, models and settings under `/v1`.
