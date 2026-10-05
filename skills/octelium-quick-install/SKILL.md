---
name: octelium-quick-install
description: >-
  Install, resume, repair or remove a single-node Octelium Cluster on one Linux VM/VPS with the
  official quick installer (https://octelium.com/install-cluster.sh), which provisions K3s,
  Multus, PostgreSQL and Valkey and bootstraps Octelium. Covers host and domain prerequisites,
  NAT/cloud firewalls (`--nat`, `--public-ip`, ports), installer options, resuming a failed run,
  post-install public DNS and TLS certificate (certbot + `octops cert`), the first login with the
  initial token, and the safe use of `--uninstall`, `--purge-data`, `--reset-db` and `--force`.
  Use for "install Octelium on a server/VPS/homelab/single node" or installer errors. Not for
  existing or multi-node Kubernetes (octelium-kubernetes-install), upgrades and certificate
  rotation of a running Cluster (octelium-cluster-ops), or managing resources
  (octelium-management).
license: Apache-2.0
compatibility: Target host is a dedicated Linux VM with root, systemd or OpenRC, 2+ vCPU, 2+ GB RAM, 20+ GB disk, amd64 or arm64, and internet access. Needs a domain the user controls.
metadata:
  author: Octelium Labs, LLC
  version: "0.1.0"
  verified-against: install-cluster.sh 2.3, octelium v0.43.0
---

# Octelium: single-node quick install

The quick installer turns a fresh Linux host into a complete Cluster: K3s (Traefik disabled,
secrets encryption on), Multus, PostgreSQL and Valkey in the `default` Kubernetes namespace,
the Octelium CLIs, and `octops init`. It is idempotent and resumable, keeps its state in
`/etc/octelium/installer`, and logs to `/var/log/octelium-install.log`. Treat it as the
controller of the installation: diagnose its state before resuming, don't hand-replicate its steps.

## Scope

- **Use for:** single-node installs on a VM/VPS/bare-metal/homelab machine, installer failures,
  post-install DNS/TLS/first login, removing an installer-managed Cluster.
- **Hand off:** existing Kubernetes (EKS/GKE/AKS/k3s/RKE2/Talos you manage) or multi-node →
  **octelium-kubernetes-install**. Upgrades, certificate renewal, health of a running Cluster →
  **octelium-cluster-ops**. Users/Services/Policies → **octelium-management**. Client
  access → **octelium-connect**.

## Ground rules

Preserve the user's authorized host and outcome across steps. Prepare the installation or
recovery plan first, then ask only for missing inputs or unresolved destructive scope. Keep
authorization for an existing-data reset separate from a request to install on a fresh host.

1. **Confirm the target host.** The installer takes over the machine: it installs K3s, may add
   firewall rules (ufw/firewalld) and a NetworkManager file, symlinks `kubectl`, writes
   `/root/.kube/config`, labels/annotates the node. Run it only on the dedicated host the user
   names, never on their workstation or an existing Kubernetes node.
2. **Use a domain the user controls.** Never invent one. It can be a subdomain
   (`octelium.example.com`). The Cluster is permanently identified by it.
3. **Check bootstrap state before resuming.** Inspect installer ownership, datastore identity,
   the `bootstrapped` marker, the `octelium` namespace and the Genesis Job. A re-run skips
   `octops init` only when the marker and namespace both exist and identity checks pass.
   Failure during init, a missing marker after success, or a missing namespace can lead to init
   again and a datastore reset. Diagnose the existing Job and establish data/backup requirements
   first (references/recovery-and-removal.md).
4. **Destructive options need informed authorization.** Don't add `--force`, `--reset-db`,
   `--uninstall`, `--purge-data` or `-y/--yes` as a troubleshooting step. Explain what each one
   destroys (references/recovery-and-removal.md) and use it only when the user asks for that
   outcome. `-y` answers the installer's own confirmation prompt; use it only for an already
   authorized operation, without asking for another yes to the same outcome.
5. **A reinstall is a reset.** Any path that runs `octops init` again (after `--uninstall`, after
   `--reset-db`, when the K3s identity changed) re-creates the Octelium namespace and truncates
   the Cluster's resource table and Valkey data: Users, Services, Policies and Credentials are
   gone even if the database directory was kept. Export resources first if they matter.
6. **`--version` is not an upgrade.** On an installed Cluster it only warns. Upgrades use
   `octops upgrade` (octelium-cluster-ops).
7. **The initial token is a root credential.** Run with `OCTELIUM_SKIP_MESSAGES=true`, passed
   explicitly through `sudo env`, so init saves it to `/etc/octelium/installer/init-token`
   (mode 0600) without printing it. Report the path only. Historical logs from unsuppressed runs
   can contain the token; filter login lines before reading them into the transcript.
8. **Long-running, root-only.** It must run as root and takes minutes (up to ~20+ on small
   hosts). Use the agent's long-running command facility or a background process with a retained
   handle/PID and private log path. Follow filtered logs; don't interrupt it or start a second
   installer while the first is running.

## Workflow

1. **Decide inputs** (ask when unknown):
   - `DOMAIN`, and access to its DNS provider.
   - Is the machine's primary interface address public? If the machine is behind NAT
     (AWS EC2, GCP, Azure, most home labs), plan `--nat`. If public-IP autodetection may fail or
     is wrong, plan `--public-ip <IPv4>`. Internal-only test lab: `--nat --force-machine-ip`.
   - Optional: `--quicv0` (QUIC tunnels, needs extra DNS per Gateway), `--enterprise`,
     `--cordium`, `--version <v>`, `--minimal` for very small hosts.
2. **Preflight on the host** (read-only): `uname -m`, `cat /etc/os-release`, `nproc`, `free -g`,
   `df -h / /var/lib /mnt`, `ip -4 route get 1.1.1.1`, `ss -lntp | grep -E ':(80|443|6443) '`,
   `command -v k3s kubeadm kubectl`. Compare the `src` address from `ip -4 route get 1.1.1.1`
   with `curl -4s https://checkip.amazonaws.com`: if they differ, the host is behind NAT. Stop
   and ask if another Kubernetes or a web server on 443 is present. For an existing
   `/etc/octelium/installer`, follow the recovery reference to establish whether resuming
   will skip init or reset data.
3. **Open the cloud firewall / security group** (the installer can't): TCP `443` (Ingress),
   UDP `53820` (WireGuard), plus UDP `8443` with `--quicv0`. TCP `80` optional.
4. **Fetch and inspect:**
   `curl -fsSL -o install-cluster.sh https://octelium.com/install-cluster.sh` then
   `bash install-cluster.sh --help`. Show the user the final command.
5. **Install:** `sudo env OCTELIUM_SKIP_MESSAGES=true bash install-cluster.sh --domain <DOMAIN> [--nat] [--public-ip IP] ...`.
   Follow `/var/log/octelium-install.log` with login lines filtered (recovery reference).
   Success ends with an `installation complete` summary; report the token path, never its value.
6. **Public DNS** (user's DNS provider): `A <DOMAIN> → <PUBLIC_IP>` and
   `CNAME *.<DOMAIN> → <DOMAIN>` (a wildcard `A` record also works). With `--quicv0`, also one
   record per Gateway hostname.
7. **TLS certificate** for `<DOMAIN>`, `*.<DOMAIN>`, `*.local.<DOMAIN>` (wildcards need a DNS-01
   challenge), then on the host:
   `octops cert <DOMAIN> --cert fullchain.pem --key privkey.pem --kubeconfig /etc/rancher/k3s/k3s.yaml`.
   Details and renewal automation: references/post-install.md.
8. **First login** from the user's own machine:
   supply the token from `/etc/octelium/installer/init-token` through `OCTELIUM_AUTH_TOKEN`, then
   run `octelium login --domain <DOMAIN>` (post-install reference; the user runs it).
   Before the real certificate is installed this fails TLS verification;
   `OCTELIUM_INSECURE_TLS=true` works for that single command.
9. **Next steps:** create named admins and an IdentityProvider, then retire `root-init`
   (octelium-management); test access with `octelium connect -p demo-nginx:9000` then
   `curl localhost:9000` (octelium-connect).

## References

| Need | File |
| --- | --- |
| Every flag and environment override, what the installer changes, file locations | [references/installer-options.md](references/installer-options.md) |
| Error messages, resuming, `--reset-db`/`--force`/uninstall/purge decisions | [references/recovery-and-removal.md](references/recovery-and-removal.md) |
| DNS records, certificates (certbot, cert-manager, renewal), first login, hardening | [references/post-install.md](references/post-install.md) |

## Sources of truth

1. `bash install-cluster.sh --help` of the downloaded script (options change between installer
   versions; this skill was written against installer 2.3).
2. Docs: https://octelium.com/docs/octelium/latest/overview/quick-install.md, and
   https://octelium.com/docs/octelium/latest/llms.txt for anything newer.
3. The bundled references.
