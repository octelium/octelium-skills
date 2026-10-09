# Troubleshooting

Docs: [Storage failures](https://octelium.com/docs/cordium/latest/management/storage.md#troubleshooting),
[task timeouts and failures](https://octelium.com/docs/cordium/latest/workspaces/runtime.md#timeouts-and-failures),
[network policies](https://octelium.com/docs/cordium/latest/workspaces/network.md),
[access control](https://octelium.com/docs/cordium/latest/management/access-control.md).

## Diagnose in layers

1. **CLI and Session.** `cordium version`; `octelium status` under a timeout. No Session means
   the next command starts a browser login (octelium-connect). Wrong Cluster: check
   `OCTELIUM_DOMAIN`/`--domain`.
2. **Authorization.** `PermissionDenied`/`Unauthorized` before any Cordium message is the
   Octelium Policy layer; Cordium messages (`... not owned by the User`,
   `The User is not a Member in this Space`) are the ownership layer
   (references/access-control.md).
3. **Start failures.** `cordium get ws <ws> -o yaml`: `status.state`, `status.failure`,
   `status.stoppingReason`; `cordium logs <ws>` while it initializes or runs. Logs are not
   retained after stop. An auto-stop job may succeed without reaching `RUNNING`.
4. **Inside the Workspace.** `cordium exec <ws> --no-stdin -- <cmd>`: task output, `env`,
   `getent hosts <svc>` for Service name resolution, `octelium status`.
5. **Kubernetes.** Pods, PVCs and events (below). Don't edit or delete Cordium-managed objects;
   the controller reconciles them.

## Messages

| Message | Cause | Action |
| --- | --- | --- |
| `You must be connected to the Cluster. Please use "octelium connect" ...` | `cordium ssh` without a tunnel | `octelium connect -d` first, or use `cordium exec`/`terminal` |
| `Workspace "<ws>" is not running (state: ...)` | `ssh`/`cp` on a stopped Workspace | `cordium start <ws>` and wait for `RUNNING` |
| `Workspace failed to start`, `Workspace stopped unexpectedly during startup` | `cordium run` saw the start fail | Read `status.failure` and `cordium logs` |
| `Workspace is stopping` | `run` during a stop | Wait for `STOPPED`, then start |
| `Workspace is already starting or running` | Start on an active Workspace | Nothing to do; attach or exec |
| `The Secret: <name> does not exist` | Short name, wrong Space, or missing Secret | Use the full `<name>.<space>.<owner>` of a Secret in the Workspace's Space |
| `GitProvider does not exist`, `NotFound` on `gitProvider` | Short or foreign GitProvider name | Full name of a GitProvider in the Template's Space |
| `Invalid Space name` | Wrong suffix | `<space>`, `<space>.<you>` or `<space>.cordium` |
| `You are not allowed to create this Space`, `This User is not authorized to become an OWNER` | ClusterConfig ownership rules | Ask an admin; don't relax the rules without a request |
| `Number of Workspaces per User has been exceeded`, `Maximum limit of active Workspaces exceeded` | Quotas | Stop or delete Workspaces, or an admin raises the ClusterConfig limit |
| `No Region accepts Workspaces` | Cordium not installed or no enabled Region | references/install.md |
| `You cannot delete the default Template` | `default` Templates are permanent | Edit it instead |
| `Secrets can only be used for ORGANIZATION Spaces`, `Cannot set Limits for USER Spaces` | USER Space restrictions | Use an ORGANIZATION Space, or Template/Workspace settings |
| `Cannot add Members to User Spaces for now` | Memberships on a personal Space | Use an ORGANIZATION Space |
| `The Volume: <v> is EXCLUSIVE and it is currently mounted by the Workspace: <ws>` | Exclusive Volume in use | Stop that Workspace or use a SHARED Volume |
| `The WorkspaceSnapshot: <s> is still being taken` | Restore before `STATE_READY` | Wait and retry |
| `Repo URL must have https scheme ...` | `git@`/`ssh://`/`http://` URL | Use the `https://` URL |
| `The type of the container command: ... must be set` | Task without `type` | Set `ON_CREATE`, `POST_START` or `PRE_STOP` |
| `Too large Dockerfile`, `Command is too large`, `Secret data is too large` | Over 5000, 5000, 1500 bytes | Use a Dockerfile URL or repository, a script in the repository, an Octelium Service |
| `Unknown field in the ClusterConfig Resource at ...` | Typo or newer field | Fix it; the field was dropped |
| `invalid --env value ...: expected KEY=VALUE` (and similar `--var`, `--port`, `--volume`) | Flag syntax | Fix the flag |

## Start failure types

`status.failure` has a `message` and one type key:

| Type | Usual cause |
| --- | --- |
| `imagePull` | Wrong image reference, private registry without `authentication`, registry unreachable |
| `imageBuild`, `buildTimeoutExceeded` | Dockerfile or devcontainer build error or too slow; read `cordium logs` |
| `repoClone`, `repoCheckout` | URL, branch or tag wrong; private repository without a token or GitProvider authorization |
| `additionalRepoClone` (`name`) | Same, for an additional repository |
| `task` (`name`, `exitCode`) | A task with `onFailure: ON_FAILURE_ABORT` exited non-zero |
| `startupTimeoutExceeded`, `startupUnknown`, `runContainer`, `healthCheck` | Node resources, image entrypoint/`cmd` exiting, runtime errors; check pods and events |
| `loadStorage`, `saveStorage` | PVC, StorageClass or snapshot restore problems |
| `networkPolicy` | The egress rules couldn't be enforced |
| `volume` (`name`) | A mounted Volume is missing, in another Space or in another Region |
| `stoppageTimeoutExceeded` | `PRE_STOP` tasks or shutdown too slow |

`status.stoppingReason`: `STOPPING_REASON_API` (a user stopped it), `STOPPING_REASON_ERROR`
(failure), `STOPPING_REASON_CLUSTER` (inactivity timeout or a stalled state).

## Silent pitfalls

These produce no error at all:

- Unknown fields in `--file`/`-f` YAML are dropped (validate with the helper).
- `spec.isEphemeral` from a `--file` is replaced by the `--ephemeral` flag (false when omitted).
- Undefined `${{ vars.X }}` references become empty strings.
- Task failures without `onFailure: ON_FAILURE_ABORT` don't stop initialization.
- Image and `ON_CREATE` changes don't reach an existing persistent Workspace or an outdated
  Template pre-build.
- `cordium exec` without `--no-stdin` kills the command when local stdin is closed.

Other workflow failures:

- Services accessed by `ON_CREATE` tasks are unavailable: `octelium connect` starts as a
  background `POST_START` task. Move Service-dependent work to `POST_START` and wait for it.
- Pre-builds have no secretless access or GitProvider token. Use public or Secret-authenticated
  git and keep Service-dependent work out of foreground pre-build tasks.
- Default-deny egress must allow DNS and public Cluster Gateway addresses for the tunnel,
  along with git and package downloads. See the network policy page above.
- A server listening only on `localhost` is unreachable through application URLs. Bind it
  to `0.0.0.0`; health-check background servers after initialization.
- Auto-stop ignores background tasks. Long jobs should stop their own Workspace after
  completion, with artifacts stored outside ephemeral storage before stopping.

## Kubernetes checks

Use the Cluster's kubeconfig (quick-install hosts: `/etc/rancher/k3s/k3s.yaml` as root).

```bash
uid="$(cordium get ws <ws> -o json | jq -r .metadata.uid)"
kubectl -n cordium get pods -o wide -l octelium.com/workspace-uid="$uid"
kubectl -n cordium describe pvc "ws-$uid"
kubectl -n cordium get events --sort-by=.lastTimestamp | tail -n 30
kubectl get nodes -l octelium.com/node-mode-cordium
kubectl -n octelium logs deploy/cordium-nocturne --since=30m | grep '<ws>'
kubectl -n octelium get pods | grep -E 'cordium|genesis'
```

- Pod `Pending`: no node labeled `octelium.com/node-mode-cordium`, or a PVC waiting for its
  StorageClass.
- Workspaces request almost no CPU or memory and are capped by their limits, so many running
  Workspaces can overcommit a node; check node memory pressure when Workspaces die or restart.
- PVC `Pending`: no default StorageClass or a wrong ClusterConfig storage rule.
- Pre-build or snapshot `unsupported`: missing VolumeSnapshot CRDs, controller or class.
