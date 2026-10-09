# Current CLI workflows

The [CLI reference](https://octelium.com/docs/cordium/latest/use/cli.md) documents the current
commands, examples and shared flags. Check `cordium <command> --help` for the installed CLI.
The separate [v0.15.0 help snapshot](cli-cordium.md) is only an offline fallback for that version;
it lacks Volumes, snapshots, `cordium code` and later fixes.

## Choose the command

| Need | Command | Reference |
| --- | --- | --- |
| Create/start and attach interactively | `cordium run [WORKSPACE]` | [Running Workspaces](https://octelium.com/docs/cordium/latest/use/cli.md#running-workspaces) |
| Create without attaching, optionally start and print JSON | `cordium create ws --file job.yaml --start -o json` | [Creating Workspaces](https://octelium.com/docs/cordium/latest/use/cli.md#creating-workspaces) |
| Start, stop or delete an existing Workspace | `cordium start`, `cordium stop`, `cordium delete ws` | [Lifecycle](https://octelium.com/docs/cordium/latest/use/cli.md#workspace-lifecycle) |
| Run a command with its exit status | `cordium exec WORKSPACE --no-stdin -- CMD` | [Executing commands](https://octelium.com/docs/cordium/latest/use/cli.md#executing-commands) |
| Follow image, repository and task output | `cordium logs WORKSPACE --timestamp --no-color` | [Logs](https://octelium.com/docs/cordium/latest/use/cli.md#logs) |
| SSH, SFTP, forwards and VS Code | `cordium ssh`, `cordium cp`, `cordium code` | [SSH and IDEs](https://octelium.com/docs/cordium/latest/use/ssh.md) |
| Save and restore Workspace storage | `cordium create snapshot NAME --workspace WORKSPACE`, `cordium create ws --snapshot NAME` | [Snapshots](https://octelium.com/docs/cordium/latest/use/cli.md#snapshots) |
| Create or mount separate persistent storage | `cordium create volume NAME --size MB`, `--volume NAME:PATH[:ro]` | [Volumes](https://octelium.com/docs/cordium/latest/use/cli.md#volumes) |
| Create a Space or Template, trigger/cancel a pre-build | `cordium create space`, `cordium create template`, `cordium build` | [Spaces and Templates](https://octelium.com/docs/cordium/latest/use/cli.md#spaces-and-templates) |
| Create Secrets, SSH keys and OAuth2 git integrations | `cordium create secret`, `cordium create usersecret --type ssh-key`, `cordium create gitprovider` | [Secrets and GitProviders](https://octelium.com/docs/cordium/latest/use/cli.md#secrets-usersecrets-and-gitproviders) |
| Read resources and capture their generated names | `cordium get KIND [NAME] -o yaml|json` | [Listing and output](https://octelium.com/docs/cordium/latest/use/cli.md#listing-and-output-formats) |
| Read/replace Cordium's Cluster-wide spec | `cordium man get cc -o yaml`, `cordium man apply PATH` | [Cluster management](https://octelium.com/docs/cordium/latest/use/cli.md#cluster-management) |

## Shared creation flags

`run` and `create workspace` accept `--file`, `--space` or `--template`, image and repository
options, env vars, `--var`, resource limits, applications, Volumes, snapshots, ephemerality,
auto-stop and container restrictions. With `--file`, flags override or extend the spec. See
the [complete flag table](https://octelium.com/docs/cordium/latest/use/cli.md#workspace-flags)
instead of inferring flags from an older help snapshot.

- `--space` and `--template` are mutually exclusive, as are `--image` and `--dockerfile`.
- `--dockerfile` embeds a local Dockerfile without a local build context. For `COPY`/`ADD`,
  configure a repository build in [the image spec](https://octelium.com/docs/cordium/latest/workspaces/image.md).
- `--env-from-secret KEY=NAME` requires a full Secret name in the Workspace's Space.
- `--cpu` uses millicores; `--memory`, `--storage` and Volume `--size` use megabytes.
- `--port` accepts `PORT`, `NAME:PORT` or `NAME:PORT:default`; `--volume` accepts
  `NAME:MOUNT_PATH[:ro]` with a Volume from the same Space.
- `--rm` belongs to `run`. `--start`, `-o json|yaml`, `--serve` and `--serve-all` belong to
  `create workspace`. `create workspace` rejects combining `--snapshot` and `--ephemeral`;
  check the installed CLI when creating an ephemeral snapshot restore.
- There is no general `cordium apply` or CLI update command. Update Workspace, Template,
  Space, Volume and UserConfig specs through the portal or APIs. `cordium man apply` is for
  ClusterConfig and replaces its entire spec.

## Automation

Create without a terminal and obtain the generated Workspace name:

```bash
ws="$(cordium create ws --file job.yaml --ephemeral -o json | jq -er .metadata.name)"
cordium start "$ws"
cordium get ws "$ws" -o yaml
```

The current reference also shows `create ws --start -o json`. If an installed CLI prints only
a notification with `--start`, use separate create/start calls as above. `--start` initiates
startup; it does not wait for `RUNNING`. For commands, wait for `RUNNING`
with a deadline, then use `exec --no-stdin`. For foreground auto-stop tasks, wait for `STOPPED`
and inspect `status.failure` and `status.stoppingReason`; successful jobs may stop before
`RUNNING`. Logs stream only while initializing or running and disappear after stop, so capture
them while the job runs. Copy artifacts from a persistent Workspace before deleting it, or
write them to a mounted Volume before an ephemeral Workspace stops.

Use [the CI/CD example](https://octelium.com/docs/cordium/latest/examples/automation/cicd.md)
or [the SDK guide](https://octelium.com/docs/cordium/latest/use/api.md) for completion handling
and cleanup. Ephemeral storage is discarded on stop; the resource remains until deleted.
