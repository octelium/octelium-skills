# Installing Cordium

Docs: [Quick installation](https://octelium.com/docs/cordium/latest/overview/quick-install.md),
[Cluster installation](https://octelium.com/docs/cordium/latest/install/cluster.md),
[CLI installation](https://octelium.com/docs/cordium/latest/install/cli.md),
[storage](https://octelium.com/docs/cordium/latest/management/storage.md),
[first steps](https://octelium.com/docs/cordium/latest/overview/first-steps.md).

Cordium is an Octelium package: it needs a working Octelium Cluster on Kubernetes, nodes
labeled for Workspaces, and a StorageClass that provisions volumes dynamically.

## Fresh single-node Cluster (quick installer)

The quick installer (installer 2.3) installs Octelium and then the package. Plan the host,
domain, firewall and DNS with the octelium-quick-install skill; the Cordium-specific options are:

| Option | Effect |
| --- | --- |
| `--cordium` | Labels the node `octelium.com/node-mode-cordium=` and, after `octops init`, runs `octops install-package <DOMAIN> --package cordium`. Records `/etc/octelium/installer/cordium-installed`, so a re-run skips it. |
| `--cordium-version <v>` | Package version (default: `--version`, else latest). Needs `--cordium`; doesn't upgrade an installed package. |
| `--longhorn` | Installs Longhorn (default StorageClass `longhorn`), the CSI snapshot CRDs and controller, and the default VolumeSnapshotClass `longhorn-snapshot-vsc`. Needs an ext4 or XFS data filesystem and iSCSI/NFS client packages (installed unless `--no-install-deps`). PostgreSQL stays on its local volume. |

```bash
curl -fsSL -o install-cluster.sh https://octelium.com/install-cluster.sh
bash install-cluster.sh --help
sudo env OCTELIUM_SKIP_MESSAGES=true bash install-cluster.sh --domain <DOMAIN> --cordium --longhorn
```

Recommend `--longhorn` for Cordium. Without it, Workspaces use the K3s `local-path` StorageClass:
Workspaces work, but Template pre-builds and WorkspaceSnapshots fail (no VolumeSnapshot API),
Volumes can't grow, and SHARED Volumes can't be provisioned. Longhorn also supports RWX shared
Volumes when configured for them. Size the host for the Workspaces
expected to run at once: each is capped at its limits (default 2 CPU cores, 6000 MB memory,
20000 MB storage; references/cluster-config.md) but reserves almost nothing, so a busy node can
be overcommitted.

## Existing Octelium Cluster

1. Label the nodes that may run Workspaces (Workspace pods are scheduled only there):
   `kubectl label nodes <node> octelium.com/node-mode-cordium=`. On a quick-install host:
   `KUBECONFIG=/etc/rancher/k3s/k3s.yaml kubectl label nodes --all octelium.com/node-mode-cordium=`.
2. Check storage: `kubectl get storageclass` (a default class, or plan ClusterConfig storage
   rules), and for pre-builds and snapshots `kubectl get volumesnapshotclass`.
3. Install the package:
   `octops install-package <DOMAIN> --package cordium [--version <v>] [--kubeconfig <path>]`.
   It asks for confirmation only in a terminal, creates the Kubernetes Job
   `octelium-genesis-init-cordium-<random>` in the `octelium` namespace and returns without
   waiting. Follow it: `kubectl -n octelium get jobs | grep genesis-init-cordium`, then
   `kubectl -n octelium logs job/<job>`.

## What the package creates

| Where | What |
| --- | --- |
| Octelium Namespace `cordium` | Service `default.cordium` (public WEB console at `https://cordium.<DOMAIN>`, also serving Workspace applications at `*.cordium.<DOMAIN>`), Service `default-ssh.cordium` (SSH proxy for Workspaces) |
| Octelium Namespace `octelium-api` | Service `default-cordium` (the Cordium gRPC API behind the Octelium API endpoint) |
| Region `default` | Marked as hosting Workspaces |
| Kubernetes namespace `octelium` | Deployments `cordium-rscserver` and `cordium-nocturne` (Workspace controller), the managed API, console and SSH Services |
| Kubernetes namespace `cordium` | Workspace pods and PVCs (`ws-<uid>`), Volume PVCs (`vol-<uid>`), a NetworkPolicy for Workspace pods |
| Cordium ClusterConfig | Default spec: any User may own Spaces (`matchAny` ALLOW); everything else uses built-in defaults |

The `default` prefix is the Region name. Don't edit these objects with `kubectl` or
`octeliumctl`; Cordium reconciles them.

## DNS and TLS

`https://cordium.<DOMAIN>` is covered by the Cluster's `*.<DOMAIN>` record and certificate.
Workspace hostnames are one level deeper: `<workspace>.cordium.<DOMAIN>`,
`<app>_<workspace>.cordium.<DOMAIN>` and `port_<port>_<workspace>.cordium.<DOMAIN>`. A DNS
wildcard matches one label only, so add a record for `*.cordium.<DOMAIN>` pointing at the
Cluster (CNAME to `<DOMAIN>`). Cordium installs a self-signed placeholder certificate for
`*.cordium.<DOMAIN>`; to serve a trusted one, obtain a certificate for `*.cordium.<DOMAIN>`
(DNS-01) and install it as the `cordium` Namespace certificate:
`octops cert <DOMAIN> --namespace cordium --cert <fullchain.pem> --key <privkey.pem>`
(octelium-cluster-ops covers certificate handling). Check what a browser receives with
`openssl s_client -connect <DOMAIN>:443 -servername test.cordium.<DOMAIN> </dev/null | openssl x509 -noout -subject -issuer -ext subjectAltName`.

## After installation

1. Grant access: admins with `octelium-api-full-access` can use everything. Other Users need a
   Policy for the Cordium API and console (references/access-control.md).
2. Install the CLI on each client (below), then as the User: `cordium run` (creates the
   personal `default` Space on first use) or open `https://cordium.<DOMAIN>`.
3. Review the ClusterConfig defaults (Space ownership, limits, timeouts): `cordium man get cc -o yaml`.
4. Optionally configure an Octelium LLM Service for the built-in Cordium Agent:
   [agent configuration](https://octelium.com/docs/cordium/latest/use/agent.md#configuring-the-agent).

## Verify

```bash
kubectl get nodes -l octelium.com/node-mode-cordium
kubectl -n octelium get deploy cordium-nocturne cordium-rscserver
octeliumctl get svc --namespace cordium
cordium get spaces
```

## Upgrade

`octops install-package <DOMAIN> --package cordium --upgrade [--version <v>]` runs the Genesis
upgrade Job (`octelium-genesis-upgrade-cordium-<random>`); follow it the same way. Keep the
`cordium` CLI close to the package version (`cordium version --check`). Octelium upgrades are
separate (octelium-cluster-ops).

## Install the CLI

The `cordium` CLI uses the Octelium Session, so install the Octelium CLIs too.

| Platform | Command |
| --- | --- |
| Linux/macOS | `curl -fsSL https://octelium.com/install-cordium.sh \| bash` (`VERSION=vX.Y.Z`, `INSTALL_DIR=...`, `USE_SUDO=false`) and `curl -fsSL https://octelium.com/install.sh \| bash` |
| Windows PowerShell | `iwr https://octelium.com/install-cordium.ps1 -useb \| iex` and `iwr https://octelium.com/install.ps1 -useb \| iex` |
| Homebrew | `brew install octelium/tap/cordium` and `brew install octelium/tap/octelium` |
| Container | `ghcr.io/octelium/cordium` |

`cordium version` prints the version; `cordium version --check` compares with the latest
release.
