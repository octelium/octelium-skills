# Resource model

Docs: [Concepts](https://octelium.com/docs/cordium/latest/overview/concepts.md),
[Spaces and Members](https://octelium.com/docs/cordium/latest/workspaces/spaces.md),
[APIs and SDKs](https://octelium.com/docs/cordium/latest/use/api.md).

Cordium resources use `apiVersion: cordium/v1`, `kind`, `metadata` (`name`, optional
`displayName`, `description`, `labels`, `annotations`, `tags`; the rest is server-managed),
`spec` and a server-managed `status`. Secret and UserSecret also carry write-only `data`. They
live in the Cordium API, not in Kubernetes and not in `octeliumctl`.

## Kinds

| Kind | Purpose | Managed with | Schema |
| --- | --- | --- | --- |
| Space | Groups Templates, Workspaces, Secrets, GitProviders, Volumes; `USER` (personal) or `ORGANIZATION` type | `cordium create space`; spec (limits, runtime, SSH) in the web console or API | `cordium.v1.Space` |
| Membership | Binds a User to a Space with a Role (`OWNER`, `ADMIN`, `USER`) | Web console or API | `cordium.v1.Membership` |
| Template | Reusable Workspace configuration; every Space has `default` | `cordium create template`, `cordium build`; edit in the web console or API | `cordium.v1.Template` |
| Workspace | The sandbox | `cordium run`, `create ws`, `start`, `stop`, `delete ws` | `cordium.v1.Workspace` |
| Secret | Space-scoped sensitive value (max 1500 bytes), never returned | `cordium create secret` | `cordium.v1.Secret` |
| GitProvider | OAuth2 app for GitHub, GitLab or a generic provider, attached to Templates | `cordium create gitprovider` | `cordium.v1.GitProvider` |
| UserSecret | Per-User sensitive value or generated SSH key | `cordium create usersecret` | `cordium.v1.UserSecret` |
| UserConfig | Per-User dotfiles, env vars, tasks, preferred Region | Web console or API | `cordium.v1.UserConfig` |
| Volume | Space-scoped persistent storage mounted by Workspaces | `cordium create volume` | `cordium.v1.Volume` |
| WorkspaceSnapshot | Point-in-time copy of a Workspace's storage | `cordium create snapshot` | `cordium.v1.WorkspaceSnapshot` |
| Region | Octelium Region enabled for Workspaces | Read only (API) | `cordium.v1.Region` |
| ClusterConfig | Cluster-wide Cordium settings (singleton) | `cordium man get cc`, `cordium man apply` | `cordium.v1.ClusterConfig` |

There is no general `apply` for Cordium resources. YAML files are consumed by
`cordium run/create ws --file` (a Workspace; only `spec` is used), `cordium create template
<name> -f` (a Template; only `spec` is used) and `cordium man apply` (a ClusterConfig document,
which needs `kind`). Other kinds are created with flags.

Schema URL pattern:
`https://octelium.com/schemas/cordium/latest/cordium.v1.<Kind>.schema.json` (bundled snapshot in
`assets/schemas/`; draft-04 with `additionalProperties: false`). Query large schemas instead of
reading them whole, e.g.

```bash
jq '.definitions | keys[]' assets/schemas/cordium.v1.Workspace.schema.json | grep -i runtime
jq '.definitions["octelium.api.main.cordium.v1.Workspace.Spec.Runtime.Task"].properties' assets/schemas/cordium.v1.Workspace.schema.json
```

## Names

Each dot-separated segment follows the Octelium rule `^[a-z][a-z0-9-]{0,38}[a-z0-9]$` (no
consecutive hyphens). Full names carry their parents; commands expand short forms with the
caller's User name:

| Kind | Full name | Short forms accepted by commands |
| --- | --- | --- |
| Space | `<space>.<owner-user>` (USER) or `<space>.cordium` (ORGANIZATION) | `<space>` → `<space>.<you>` |
| Template, Secret, GitProvider, Volume | `<name>.<space>.<owner>` | `<name>` → `<name>.default.<you>`; `<name>.<space>` → `<name>.<space>.<you>` |
| UserSecret, WorkspaceSnapshot | `<name>.<you>` | `<name>` |
| Workspace | Generated: 3 to 6 lowercase characters, starting with a letter | Exact name only |

Consequences:

- `cordium create space team` creates the personal `team.<you>`. An organization Space is
  created with the explicit suffix: `cordium create space team.cordium` (allowed only if the
  ClusterConfig ownership rules allow it). Its children are then `<name>.team.cordium`.
- References inside specs are matched against the stored full name without expansion:
  `fromSecret`, the Template `gitProvider`, `--env-from-secret KEY=<secret>`,
  `--client-secret-from-secret` and `--git-provider` must be full names, e.g.
  `fromSecret: anthropic-key.agents.alice`. A short name fails with
  `The Secret: <name> does not exist` or `NotFound`. Exception: Volume names in `volumeMounts`
  and `--volume` are short names resolved in the Workspace's Space (or full names).
- `fromUserSecret` in UserConfig must be `<name>.<you>`.
- `cordium get tmpl|sec|gp|vol` without `--space` lists your personal `default` Space;
  `cordium get spaces` lists only Spaces you created (Spaces you joined appear in the web
  console).
- Qualify GitProvider names with their Space; use the documented `cordium create gitprovider
  <name>.<space>.<owner>` form.

## Quotas and built-in defaults

| Item | Limit or default | Configurable in ClusterConfig |
| --- | --- | --- |
| Spaces created per User | 150 | No |
| Workspaces per User | 1000 | `workspace.limit.maxPerUser` |
| Non-stopped Workspaces per User | 128 | `workspace.limit.maxActivePerUser` |
| Templates per Space | 1000 | No |
| Secrets per Space, value size | 1000, 1500 bytes | No |
| GitProviders per Space | 100 | No |
| Members per Space | 2000 | No |
| UserSecrets per User | 1000 | No |
| WorkspaceSnapshots per User | 100 | `workspace.limit.maxSnapshotsPerUser` |
| Volumes per Space; Volume size | 64; default 10000 MB, minimum 1000 MB | `volume.limit.maxPerSpace`, `defaultSize`, `maxSize` |
| Workspace CPU, memory, storage | 2000 millicores, 6000 MB, 20000 MB | `workspace.limit.default*SpaceLimit`, `maxLimit` |
| Inactivity timeout | 30 hours | `workspace.timeout.*` |

## Status fields worth reading

- Workspace: `status.state`, `status.failure` (with a typed reason), `status.hostname`,
  `status.limit` (effective limits), `status.sessionRef`, `status.templateRef`,
  `status.spaceRef`, `status.run`/`lastRuns`, `status.stoppingReason`,
  `status.workspaceSnapshotRef`.
- Template: `status.buildInfo.builds[]` (`state`, `failure`), `currentReadyBuildID`.
- Space: `status.type` (`USER`, `ORGANIZATION`), `status.userRef` (creator).
- Volume and WorkspaceSnapshot: `status.state`, `status.failure`, `status.regionRef`.
