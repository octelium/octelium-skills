# Storage: Workspace volumes, Volumes and WorkspaceSnapshots

Docs: [Storage backends](https://octelium.com/docs/cordium/latest/management/storage.md),
[Volumes](https://octelium.com/docs/cordium/latest/workspaces/volumes.md),
[snapshots](https://octelium.com/docs/cordium/latest/workspaces/snapshots.md),
[storage selection](https://octelium.com/docs/cordium/latest/management/clusterconfig.md#storage).
Worked examples: [sharing data](https://octelium.com/docs/cordium/latest/examples/workflows/volumes.md),
[checkpoints and forks](https://octelium.com/docs/cordium/latest/examples/workflows/snapshots.md).

## Backend requirements

| Feature | Needs |
| --- | --- |
| Any Workspace | A StorageClass with dynamic provisioning (ReadWriteOnce): the default class, or a ClusterConfig rule |
| Template pre-builds, WorkspaceSnapshots | The CSI VolumeSnapshot API, a snapshot-capable driver and a VolumeSnapshotClass (the driver's default, or a ClusterConfig rule) |
| SHARED Volumes | A ReadWriteMany class (NFS, CephFS, EFS, ...) selected by a ClusterConfig `volume.storage.storageClass` rule |
| Growing a Volume | A StorageClass with `allowVolumeExpansion` |

The quick installer's `--longhorn` provides snapshots and expansion; Longhorn RWX Volumes can
also provide shared storage when configured for it. K3s `local-path` supports Workspace and
exclusive Volume storage, without snapshots, expansion or shared mounts. Check with `kubectl get storageclass` and
`kubectl get volumesnapshotclass`. Selection rules: references/cluster-config.md.

Each Workspace's storage is the PVC `ws-<workspace-uid>` in the Kubernetes namespace `cordium`,
sized by its storage limit. It holds the whole Workspace filesystem; an ephemeral Workspace's
storage is discarded on every stop, a persistent one's when the Workspace is deleted.

## Volumes

A Volume is Space-scoped storage with its own lifecycle, mounted by Workspaces of the same Space
at arbitrary paths. It outlives Workspaces and is never included in WorkspaceSnapshots.

```bash
cordium create volume datasets.my-project --size 50000              # ADMIN or OWNER
cordium create volume cache.my-project --size 20000 --shared
cordium get vol --space my-project
cordium create ws --space my-project --volume datasets:/data:ro --volume cache:/cache
```

- `--size` is in MB: default 10000, minimum 1000, capped by ClusterConfig `volume.limit.maxSize`.
  Volumes can grow (web console or `UpdateVolume`) but never shrink.
- Access modes: `ACCESS_MODE_EXCLUSIVE` (default) is mounted by one non-stopped Workspace at a
  time (`The Volume: <name> is EXCLUSIVE and it is currently mounted by the Workspace: <ws>`);
  `ACCESS_MODE_SHARED` (`--shared`) allows concurrent mounts. The mode is immutable.
- A Volume lives in one Region (`--region`, default your preferred Region); Workspaces mounting
  it run there, and starting fails if their storage or snapshot is in another Region.
- States: `STATE_PENDING` (can already be mounted; many backends provision on first use),
  `STATE_READY`, `STATE_FAILED` (`unsupported`, `storage`, `unknown`).
- Mounts: `runtime.volumeMounts[]` with the short Volume name, an absolute canonical
  `mountPath` and `readOnly`, or `--volume NAME:PATH[:ro]`. At most 16 per Workspace (and
  ClusterConfig `volume.limit.maxMountsPerWorkspace`), no duplicates or overlapping paths, and
  not `/`, `/workspace`, `/tmp`, `/etc`, `/usr`, `/var`, `/root` or anything under `/dev`,
  `/proc`, `/sys`, `/run`, `/octelium`, `/var/lib/containers`, `/var/lib/docker`. Template
  mounts are added to the Workspace's own.
- An existing mount directory must be empty. A new Volume is owned by the Workspace user of
  the first Workspace that mounts it read-write. Mounts apply on every start.
- Deleting is refused while any Workspace or Template of the Space mounts it, running or not;
  remove the mounts first. Deletion destroys the data.

## WorkspaceSnapshots

A WorkspaceSnapshot copies a Workspace's storage at a point in time, owned by its creator.

```bash
cordium create snapshot before-upgrade --workspace abc
cordium get snap before-upgrade -o yaml            # wait for status.state STATE_READY
cordium create ws --snapshot before-upgrade --start
cordium delete snap before-upgrade
```

- Taken without stopping the Workspace: from a running Workspace it is crash-consistent
  (`CONSISTENCY_CRASH`), from a stopped one clean (`CONSISTENCY_CLEAN`). Stop the Workspace
  first when consistency matters (databases).
- The Workspace needs persistent storage that exists: it must have run at least once, and an
  ephemeral Workspace only while it runs. Build Workspaces can't be snapshotted.
- Restoring creates a new Workspace in the snapshot's Space and Region, from the source
  Workspace's Template unless `--template`/`--space` is given (still the same Space). It starts
  from the copied filesystem and skips image pulls/builds, clones, dotfiles and `ON_CREATE`
  tasks. `POST_START`, env vars, network rules, mounts and secretless access apply normally.
  Storage is at least as large as the snapshot. Persistent Workspaces restore only on the
  first run; ephemeral ones restore on every run. `cordium create ws` rejects combining
  `--snapshot` and `--ephemeral`; use the API/SDK or check `cordium run --help` for that mode.
- `STATE_FAILED` with `unsupported` means no VolumeSnapshot support; `sourceNotFound` means the
  Workspace's storage is gone.
- Deleting is refused while a Workspace restored from it hasn't run yet, or while an ephemeral
  Workspace restores from it on every run.
- Default quota: 100 per User (`workspace.limit.maxSnapshotsPerUser`).
- Deleting the source Workspace does not delete its snapshots. Mounted Volumes are not
  included in snapshots or pre-builds: restored Workspaces mount their current content.
- Restore storage must use the same CSI driver as its source snapshot. Check storage rules
  when Templates or Workspaces are routed to different drivers.
