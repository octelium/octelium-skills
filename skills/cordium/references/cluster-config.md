# Cordium ClusterConfig

Docs: https://octelium.com/docs/cordium/latest/use/clusterconfig.md
Schema: https://octelium.com/schemas/cordium/latest/cordium.v1.ClusterConfig.schema.json

One Cordium ClusterConfig (`default`) holds the Cluster-wide Cordium settings. It is separate
from the Octelium ClusterConfig (`octeliumctl get cc`). Reading and changing it calls the
`octelium.api.main.cordium.v1.ManagementService`, which needs an explicit Policy
(references/access-control.md).

## Change it safely

```bash
cordium man get cc -o yaml > cordium-cc.yaml
# edit only what was asked; keep everything else, especially spec.space.ownership
uv run "$cordium_skill_dir/scripts/validate_resources.py" cordium-cc.yaml
cordium man apply cordium-cc.yaml
cordium man get cc -o yaml
```

`cordium man apply <file|dir|->` loads every YAML document (each needs `kind`), applies only
the `ClusterConfig` one and ignores the rest. It **replaces the entire spec**: an omitted
section returns to built-in behavior. Unknown fields print
`Unknown field in the ClusterConfig Resource at ...` and are dropped; treat that as an error.
The exported file's `status` and server-managed metadata are ignored on apply. Settings take
effect on the next request or Workspace start; running Workspaces keep their resolved limits.

The installation default:

```yaml cordium
kind: ClusterConfig
metadata:
  name: default
spec:
  space:
    ownership:
      rules:
        - effect: ALLOW
          condition:
            matchAny: true
```

## `spec.space.ownership`

Decides who may create (own) Spaces, including each User's automatic `default` Space and new
OWNER Memberships. DENY rules are evaluated first, then ALLOW rules; no match denies. A rule
whose condition fails to evaluate is skipped. **Without rules nobody can create a Space**, so
new Users can't even start their first Workspace.

Conditions use the Octelium condition types (`match`, `not`, `matchAny`, `all`, `any`, `none`,
`opa`) over `ctx.user` (the Octelium User: `metadata.name`, `spec.type`, `spec.email`,
`spec.groups`, `spec.attrs`) and `ctx.space` (the Space being created: `metadata.name` with its
owner suffix, `status.type` `USER` or `ORGANIZATION`):

```yaml fragment
spec:
  space:
    ownership:
      rules:
        - effect: ALLOW                      # everyone gets personal Spaces
          condition:
            match: ctx.space.status.type == "USER"
        - effect: ALLOW                      # only platform admins create organization Spaces
          condition:
            match: '"platform-admins" in ctx.user.spec.groups'
        - effect: DENY                       # DENY wins over any ALLOW
          condition:
            match: '"suspended" in ctx.user.spec.groups'
```

## `spec.workspace`

| Field | Meaning | Built-in default |
| --- | --- | --- |
| `limit.maxPerUser` | Workspaces a User may own | 1000 |
| `limit.maxActivePerUser` | Non-stopped Workspaces per User | 128 |
| `limit.maxSnapshotsPerUser` | WorkspaceSnapshots per User | 100 |
| `limit.defaultUserSpaceLimit`, `limit.defaultOrganizationSpaceLimit` | Defaults for dimensions that the Workspace or Template doesn't set, by Space type | 2000 millicores, 6000 MB, 20000 MB |
| `limit.maxLimit` | Hard cap for every Workspace | None |
| `limit.buildLimit` | Resources of pre-build Workspaces | 2000 millicores, 6000 MB, 20000 MB |
| `timeout.userSpaceDuration`, `timeout.organizationSpaceDuration`, `timeout.defaultDuration` | Inactivity before a `RUNNING` Workspace is stopped: by Space type, else the default | 30 hours |
| `timeout.allowNoTimeout` | Lets a Workspace's own `runtime.timeout.mode: DISABLED` take effect | false |
| `timeout.maxActiveDuration` | Present in the schema; not enforced in the source checked | |
| `runtime.capabilities.add/drop` | Linux capabilities added to and dropped from every Workspace | None |
| `storage.storageClass.rules[]` | `condition` and `storageClass` for Workspace volumes; first match wins, else the default StorageClass | Default class |
| `storage.volumeSnapshotClass.rules[]` | `condition` (over `ctx.workspace`, `ctx.template`) and `volumeSnapshotClass` for pre-builds and WorkspaceSnapshots | The driver's default class |

Limits use `cpu.millicores`, `memory.megabytes`, `storage.megabytes`; durations use one unit
(`minutes`, `hours`, `days`, ...). Terminals, `exec`, SSH sessions and application traffic count
as activity.

In the source checked, Workspace `storageClass` rule conditions can't read the Workspace (it
isn't passed under `ctx`), so only `matchAny: true` rules match; other rules are skipped. Use
one class for all Workspaces until this changes, and verify with
`kubectl -n cordium get pvc ws-<workspace-uid> -o jsonpath='{.spec.storageClassName}'`.

```yaml fragment
spec:
  workspace:
    limit:
      maxPerUser: 30
      maxActivePerUser: 5
      defaultUserSpaceLimit:
        cpu: {millicores: 2000}
        memory: {megabytes: 4096}
        storage: {megabytes: 20000}
      maxLimit:
        cpu: {millicores: 16000}
        memory: {megabytes: 32768}
        storage: {megabytes: 200000}
    timeout:
      defaultDuration: {hours: 8}
      organizationSpaceDuration: {hours: 24}
    storage:
      storageClass:
        rules:
          - condition: {matchAny: true}
            storageClass: longhorn
      volumeSnapshotClass:
        rules:
          - condition: {matchAny: true}
            volumeSnapshotClass: longhorn-snapshot-vsc
```

## `spec.volume`

| Field | Meaning | Built-in default |
| --- | --- | --- |
| `limit.maxPerSpace` | Volumes per Space | 64 |
| `limit.defaultSize`, `limit.maxSize` | Size when none is requested; hard cap (`megabytes`) | 10000 MB; 10,000,000 MB |
| `limit.maxMountsPerWorkspace` | Mounts per Workspace | 16 (hard limit) |
| `storage.storageClass.rules[]` | `condition` over `ctx.volume` and `storageClass`; first match wins, else the default class | Default class |

SHARED Volumes need a ReadWriteMany class:

```yaml fragment
spec:
  volume:
    storage:
      storageClass:
        rules:
          - condition:
              match: ctx.volume.spec.accessMode == "ACCESS_MODE_SHARED"
            storageClass: nfs-client
```

A complete, validated starting point: `assets/templates/cluster-config.yaml`.
