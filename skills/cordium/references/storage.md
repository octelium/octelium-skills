# Storage: Workspace volumes, Volumes and WorkspaceSnapshots

Docs: https://octelium.com/docs/cordium/latest/install/cluster.md,
https://octelium.com/docs/cordium/latest/use/clusterconfig.md

Volumes and WorkspaceSnapshots are newer than v0.15.0: check `cordium create --help` for
`volume` and `snapshot` before using them.

## Backend requirements

| Feature | Needs |
| --- | --- |
| Any Workspace | A StorageClass with dynamic provisioning (ReadWriteOnce): the default class, or a ClusterConfig rule |
| Template pre-builds, WorkspaceSnapshots | The CSI VolumeSnapshot API, a snapshot-capable driver and a VolumeSnapshotClass (the driver's default, or a ClusterConfig rule) |
| SHARED Volumes | A ReadWriteMany class (NFS, CephFS, EFS, ...) selected by a ClusterConfig `volume.storage.storageClass` rule |
| Growing a Volume | A StorageClass with `allowVolumeExpansion` |

The quick installer's `--longhorn` provides the first two and expansion; K3s `local-path` gives
only plain Workspaces. Check with `kubectl get storageclass` and
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
  from the copied filesystem and skips `ON_CREATE` tasks. `cordium create ws` doesn't combine
  `--snapshot` with `--ephemeral`.
- `STATE_FAILED` with `unsupported` means no VolumeSnapshot support; `sourceNotFound` means the
  Workspace's storage is gone.
- Deleting is refused while a Workspace restored from it hasn't run yet, or while an ephemeral
  Workspace restores from it on every run.
- Default quota: 100 per User (`workspace.limit.maxSnapshotsPerUser`).
