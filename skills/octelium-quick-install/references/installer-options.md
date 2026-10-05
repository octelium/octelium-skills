# Quick installer reference (install-cluster.sh 2.3)

Source: https://octelium.com/install-cluster.sh. Always check `bash install-cluster.sh --help` of
the copy you downloaded; this file mirrors installer version 2.3.

## Usage

```bash
sudo env OCTELIUM_SKIP_MESSAGES=true bash install-cluster.sh --domain example.com [options]
sudo bash install-cluster.sh --uninstall [--purge-data]
bash install-cluster.sh --help
bash install-cluster.sh --print-manifests [--domain example.com]   # no root needed; prints generated manifests, passwords redacted
```

## Options

| Option | Effect |
| --- | --- |
| `--domain <fqdn>` | Cluster domain. Required on the first run; afterwards read from state. A different domain than the stored one is refused without `--force`. |
| `--public-ip <ipv4>` | Public IPv4 used for the Gateway (WireGuard) address. Auto-detected via public IP echo services when omitted; must be a routable unicast address. |
| `--nat` | The machine is behind NAT: the Region external IP (Ingress) becomes the machine's primary interface address instead of the public IP. Only takes effect at bootstrap. |
| `--force-machine-ip` | Publish the machine's primary address (not the public IP) as the Gateway address. For private/internal test networks; use with `--nat`. |
| `--version <v>` | Octelium version for bootstrap (and pins the CLI install). Default `latest`. Does **not** upgrade an installed Cluster. |
| `--quicv0` | Also enable QUIC tunnels (UDP `8443` by default). Experimental. |
| `--cordium` | Install the Cordium package (also labels the node for Cordium). |
| `--enterprise` | Install the Octelium Enterprise package. |
| `--db-dir <path>` | PostgreSQL host directory (default `/mnt/octelium/db`). Changing it later is refused without `--force`. |
| `--db-size <size>` | PV/PVC capacity (default `20Gi`). Can't be changed after creation. |
| `--reset-db` | Move an unrecognized database directory aside (`<dir>.bak.<timestamp>`) and start empty. Destructive for the Cluster's state; see recovery-and-removal.md. |
| `--minimal` | Disable K3s metrics-server for very small hosts. |
| `--k3s-version <v>` | Pin K3s (e.g. `v1.33.4+k3s1`); default is the `stable` channel. |
| `--no-install-deps` | Don't install missing host packages (curl, iproute2, openssl, ...). |
| `--no-firewall` | Don't add ufw/firewalld rules. |
| `--no-networkmanager` | Don't write `/etc/NetworkManager/conf.d/00-octelium-k3s.conf`. |
| `--skip-port-check` | Don't check that TCP 80/443/6443 are free. |
| `--skip-image-prepull` | Don't pre-pull PostgreSQL/Valkey/Multus images. |
| `--uninstall` | Remove the installer-owned K3s (and firewall/NetworkManager changes). Keeps the database and credentials. |
| `--purge-data` | With `--uninstall`: also delete the database directory and `/etc/octelium/installer`. |
| `--force` | Proceed past ownership and safety checks (foreign K3s, domain/db-dir mismatch, node count, Cluster identity change). |
| `-y`, `--yes` | Answer yes to the installer's destructive confirmations (required when there is no TTY). |

## Environment overrides

`OCTELIUM_K3S_CHANNEL`, `OCTELIUM_K3S_VERSION`, `OCTELIUM_K3S_EXTRA_ARGS` (must not override
`--data-dir`, `--write-kubeconfig`, `--write-kubeconfig-mode`), `OCTELIUM_K3S_INSTALL_URL`,
`OCTELIUM_K3S_INSTALL_SHA256`, `OCTELIUM_INSTALL_URL`, `OCTELIUM_INSTALL_SHA256` (verify
downloaded installers), `OCTELIUM_PG_IMAGE` (default `postgres:17-alpine`), `OCTELIUM_PG_MAJOR`
(17), `OCTELIUM_PG_RUN_UID/GID` (70/70), `OCTELIUM_VALKEY_IMAGE`, `OCTELIUM_VALKEY_RUN_UID/GID`,
`OCTELIUM_MULTUS_IMAGE`, `OCTELIUM_DB_DIR`, `OCTELIUM_DB_SIZE`, `OCTELIUM_STATE_DIR`,
`OCTELIUM_{PG,VALKEY,MULTUS}_{CPU,MEMORY}_REQUEST`, `OCTELIUM_K3S_POD_CIDR` (10.42.0.0/16),
`OCTELIUM_K3S_SERVICE_CIDR` (10.43.0.0/16), `OCTELIUM_WIREGUARD_PORT` (53820),
`OCTELIUM_QUIC_PORT` (8443).

For agent-run installation, pass `OCTELIUM_SKIP_MESSAGES=true` through `sudo env` as above.
`octops init` inherits it and suppresses the token-bearing login message while still saving
the token to the installer's private file. Do not rely on sudo preserving the caller's environment.

## What a run does (in order)

1. Parse and validate arguments; require root; take the lock `/run/lock/octelium-installer.lock`;
   start logging to `/var/log/octelium-install.log` (mode 0600).
2. Install missing host tools (apt/dnf/yum/zypper/apk/pacman; `kernel-modules-extra` on RHEL-family 10).
3. Load state from `/etc/octelium/installer`; prepare the database directory and its marker file
   `.octelium-installer` (records domain, PostgreSQL major, UID/GID).
4. Preflight warnings: RAM < 2 GiB, < 2 CPUs, low disk, another Kubernetes present. Port check:
   6443 busy is fatal; 80/443 busy is a warning.
5. Resolve the primary interface and public IPv4; warn if `<DOMAIN>` doesn't resolve to it yet
   (not fatal: DNS can be set after install).
6. NetworkManager unmanaged-devices file; ufw/firewalld rules for pod/service CIDRs and
   80/tcp, 443/tcp, WireGuard UDP (and QUIC UDP).
7. Install the Octelium CLIs (`octelium`, `octeliumctl`, `octops`) to `/usr/local/bin`.
8. Install or reuse K3s (`--disable=traefik --secrets-encryption`), wait for the API and node,
   refuse multi-node Clusters, record the K3s cluster UID.
9. Label the node (`octelium.com/node`, `node-mode-controlplane`, `node-mode-dataplane`), remove
   control-plane taints, annotate `octelium.com/override-gw-ip`.
10. Pre-pull images; create credentials, storage (local PV), Multus, PostgreSQL and Valkey; wait
    for them and verify authentication.
11. Bootstrap with `octops init <DOMAIN> --version <v> --bootstrap -` (skipped when already
    bootstrapped and the namespace still exists). The initial token is saved to
    `/etc/octelium/installer/init-token`; the environment override above suppresses its printout.
12. Install `--cordium`/`--enterprise` packages (`octops install-package`), print the summary.

## Files and locations

| Path | Content |
| --- | --- |
| `/etc/octelium/installer/` (0700) | State: `domain`, `db-dir`, `db-size`, `postgres-password`, `valkey-password`, `k3s-owned`, `cluster-uid`, `bootstrapped`, `cluster-version`, `init-token`, package markers, firewall/NetworkManager records |
| `/var/log/octelium-install.log` | Full log of every run; unsuppressed historical runs can contain a login command with the token |
| `/etc/rancher/k3s/k3s.yaml` | Kubeconfig (also copied to `/root/.kube/config` if absent) |
| `/mnt/octelium/db` (default) | PostgreSQL data + `.octelium-installer` marker |
| `/var/lib/rancher/k3s` | K3s data; CNI conf dir `/var/lib/rancher/k3s/agent/etc/cni/net.d` |

The PostgreSQL and Valkey passwords live in the state directory and in Kubernetes Secrets
`octelium-pg` / `octelium-valkey` in the `default` namespace; the Bootstrap (with those
passwords) is also stored by `octops init` in the `default/octelium-init` Secret. Protect root
and backups of this host accordingly.
