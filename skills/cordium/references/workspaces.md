# Running Workspaces

Docs: https://octelium.com/docs/cordium/latest/use/cli.md,
https://octelium.com/docs/cordium/latest/use/overview.md

## Lifecycle

A Workspace is created `STOPPED` with a generated name; a start moves it through
`INIT_REQUEST` → `INITIALIZING` → `PULLING_IMAGE`/`BUILDING_IMAGE` → `STARTING_RUNTIME` →
`PREPARING` (clone, dotfiles, devcontainer features, `ON_CREATE` and `POST_START` tasks) →
`RUNNING`. A stop goes `STOPPING_REQUEST` → `STOPPING` (`PRE_STOP` tasks) → `STOPPED`. A failed
start ends `STOPPED` with `status.failure` (references/troubleshooting.md).

| Watchdog | Value |
| --- | --- |
| Stuck in `INIT_REQUEST` | Set to `STOPPED` after 5 minutes |
| Still starting (pre-running states) | Stopped after 180 minutes |
| `ON_CREATE` + `POST_START` tasks | 60 minutes on fresh runs and pre-builds, 20 minutes otherwise |
| `PRE_STOP` tasks | 10 minutes |
| `RUNNING` without activity | Stopped after the inactivity timeout (default 30 hours, references/cluster-config.md) |

**Fresh runs.** The first successful run of a persistent Workspace and every run of an
ephemeral one pull or build the image and run `ON_CREATE` tasks. Later starts of a persistent
Workspace reuse its stored filesystem and container: `POST_START` tasks run again, the image is
not rebuilt, and image or `ON_CREATE` changes need a new Workspace. A Workspace restored from a
Template pre-build or a WorkspaceSnapshot starts from that storage and skips `ON_CREATE`.

**Persistent vs ephemeral.** Persistent (the default) keeps the whole filesystem, including
installed packages, across stops. `--ephemeral` (`spec.isEphemeral`) discards storage on every
stop; pass the flag even with `--file`, because the CLI replaces the file's `isEphemeral` with
it. `--rm` (only `cordium run`) deletes the Workspace when the terminal session ends.

Each start creates a new Octelium Session for the run (references/access-control.md) and picks
a Region: the Region of existing storage, Volumes or the snapshot, else the User's preferred
Region, else any Region accepting Workspaces.

## Interactive use

```bash
cordium run                                            # default Template of your default Space
cordium run --template backend.my-project              # a Template (personal Space my-project)
cordium run --space my-project                         # that Space's default Template
cordium run --file workspace.yaml -e LOG_LEVEL=debug   # YAML plus overrides
cordium run --image python:3.12-slim --ephemeral --rm  # throwaway sandbox
cordium run abc                                        # attach to abc, starting it if stopped
cordium terminal abc                                   # another terminal in a running Workspace
```

`cordium run` waits for `PREPARING` or `RUNNING`, then attaches an interactive terminal; the
Workspace keeps running after the terminal exits unless `--rm` was given. Creation flags work
with `run` and `create ws` alike: `--file`, `--template` or `--space` (mutually exclusive),
`--image` or `--dockerfile` (mutually exclusive; a local Dockerfile is embedded inline, without
build context), `--repository` with `--branch`, `--depth`, `--checkout`, `--additional-repo
NAME=URL`, `-e KEY=VALUE`, `--env-from-secret KEY=<full Secret name>`, `--var NAME=VALUE`,
`--cpu` (millicores), `--memory` and `--storage` (MB), `--port NAME:PORT[:default]` or `PORT`,
`--auto-stop`, `--read-only`, `--cap-add`, `--cap-drop`, and after v0.15.0
`--volume NAME:PATH[:ro]` and `--snapshot NAME`. Flags extend or override the `--file` spec.

`cordium run --serve-all/--serve` are accepted but not applied in v0.15.0 and the source
checked; use `cordium create ws --serve-all ...` or `runtime.octelium` in the YAML.

## Agents, scripts and CI

Avoid the interactive terminal. In a CI script: create, start, wait, execute, clean up.

```bash
ws="$(cordium create ws --file job.yaml --ephemeral -o json | jq -r .metadata.name)"
cordium start "$ws" --var TASK="run the unit tests"
for _ in $(seq 1 120); do
  state="$(cordium get ws "$ws" -o json | jq -r .status.state)"
  case "$state" in RUNNING|STOPPED) break ;; esac
  sleep 5
done
if [ "$state" = RUNNING ]; then
  cordium exec "$ws" --no-stdin -w /workspace/repo -- make test; rc=$?
else
  cordium get ws "$ws" -o json | jq '.status.failure'; rc=1
fi
cordium delete ws "$ws"
exit "$rc"
```

- `cordium create ws --start` starts immediately but then prints a message instead of `-o`
  output; create with `-o json`, then `cordium start`, when you need the name.
- `STOPPED` after a start means failure: read `.status.failure` and `cordium logs "$ws"`.
- `cordium exec` runs the command as the Workspace User (`--root` for root) through a shell:
  each argument is quoted, so use `-- sh -c '...'` for pipes and redirects. It forwards stdout,
  stderr and the exit code. Always pass `--no-stdin` unless you stream input: without it, end
  of file on the local stdin (`</dev/null`, closed stdin in agent shells and CI, the end of a
  piped input) kills the remote command. Move files with `cordium cp` instead of piping them.
- For one-shot jobs, put the work in `POST_START`/`ON_CREATE` tasks with
  `runtime.autoStop: true` (`--auto-stop`): the Workspace stops after its non-background tasks
  finish. Follow it with `cordium logs`.
- Per-run variables: `cordium start <ws> --var NAME=VALUE` overrides Workspace and Template
  `vars` for that run only.
- `cordium stop` without a name inside a Workspace stops that Workspace (`CORDIUM_NAME`).

## SSH, files and editors

`cordium ssh` and `cordium cp` reach the Workspace through the Octelium Service
`<region>-ssh.cordium`, so the client must be connected (`octelium connect -d`, or
`sudo -E octelium connect` in the foreground; octelium-connect). `cordium ssh` refuses with
`You must be connected to the Cluster` otherwise. The SSH user is the Workspace name;
authentication is the Octelium identity, no keys.

```bash
cordium ssh abc                                  # shell
cordium ssh abc -- uptime                        # one command
cordium ssh abc -N -L 5432:localhost:5432        # port forward
cordium ssh abc -N -D 1080                       # SOCKS5 through the Workspace
cordium ssh abc --print-config >> ~/.ssh/config  # Host cordium-abc for ssh, scp, rsync, editors
cordium cp ./data.csv abc:/workspace/repo/data.csv
cordium cp -r abc:/workspace/repo/dist ./dist
cordium cp abc:/workspace/repo/model.pt def:/workspace/repo/model.pt
```

The printed SSH config disables host key checking for that host; tell the user before
appending it. SSH is denied when the Space sets `authorization.disableSSH`.

## Applications

`spec.applications` (or `--port`) name ports inside the Workspace. The console proxy serves:

| URL | Target |
| --- | --- |
| `https://<ws>.cordium.<DOMAIN>` | The application with `isDefault: true` |
| `https://<app>_<ws>.cordium.<DOMAIN>` | A named application |
| `https://port_<port>_<ws>.cordium.<DOMAIN>` | Any port |

Non-default Regions add the Region: `<ws>.<region>.cordium.<DOMAIN>`. Only the owner can open
them unless an application is shared with the Space's Members or all Users (web console
"share", API `ShareWorkspacePort`). These hostnames need the `*.cordium.<DOMAIN>` DNS record and
certificate (references/install.md). Application traffic counts as activity for the inactivity
timeout.

## Inside a Workspace

| Item | Value |
| --- | --- |
| User | An existing `octelium` user, else the image's UID 1000 user (e.g. `ubuntu`, `node`), else a created `octelium` (UID 1000); `sudo` and `runAsRoot`/`--root` give root |
| Repositories | Primary at `/workspace/repo`; additional at `/workspace/additional-repos/<name>` |
| Environment | `CORDIUM_NAME`, `CORDIUM_HOSTNAME`, `OCTELIUM_DOMAIN`, `OCTELIUM_AUTH_PROXY_SOCKET`, `OCTELIUM_HOME=mem`, `SSH_AUTH_SOCK` (agent with SSH-key UserSecrets) plus the spec's env vars |
| Octelium | `octelium connect` runs as a background task with the Workspace Session and a local DNS server: reach Services as `<svc>`, `<svc>.<ns>` or `<svc>.<ns>.local.<DOMAIN>` |
| Containers | Podman works inside (rootful as root); devcontainer features such as docker-in-docker can be added |

Secretless access example from inside a Workspace, for a `POSTGRES` Service named `pg-prod`
that injects its own credentials: `psql "host=pg-prod user=app dbname=app"`. The connection is
authorized per request against the owner's Policies; nothing secret is stored in the Workspace.

## Snapshots and Volumes

Newer than v0.15.0 (check `cordium create --help`); details in references/storage.md.

```bash
cordium create snapshot before-upgrade --workspace abc   # asynchronous; wait for STATE_READY
cordium get snap before-upgrade -o yaml
cordium create ws --snapshot before-upgrade --start      # new Workspace from it, same Space
cordium create volume datasets.my-project --size 50000
cordium create ws --space my-project --volume datasets:/data:ro
```
