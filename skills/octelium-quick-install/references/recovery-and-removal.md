# Recovery, re-runs and removal

## How a failed run reports

On failure the installer prints the failing line and command, `full log: /var/log/octelium-install.log`,
`rerunning this script resumes from where it stopped`, then non-Running pods and recent warning
events. Datastore failures also dump the pod description and logs. Read those first.

Default recovery loop: identify the cause → fix it on the host → re-run the exact same command.
State (domain, db-dir, credentials, K3s ownership, bootstrap status) is reused. After a
successful bootstrap, re-runs skip `octops init` and are safe.

## Common errors

| Message (abridged) | Cause | Fix |
| --- | --- | --- |
| `must run as root` | Not root | `sudo bash install-cluster.sh ...` |
| `another Octelium installer is already running (PID n)` | Concurrent run | Wait for it; a stale lock is removed automatically. |
| `--domain is required` / `invalid Cluster domain` | Missing/invalid FQDN | Pass a valid domain (letters, digits, hyphens, at least one dot). |
| `installer state belongs to domain X, not Y (use --force to override)` | Different domain than the stored one | Use the original domain. Changing it means a new Cluster; see "Changing domain" below. |
| `TCP 6443 is already in use by ...` | Another Kubernetes/API server | Stop it or use another host. `--skip-port-check` only if you know it will free the port. |
| `TCP 80/443 is already in use` (warning) | Web server running | Stop/disable it (nginx, apache, caddy); the Ingress needs 443. |
| `could not detect a public IPv4 address; pass it explicitly with --public-ip (or use --nat)` | No outbound access to IP echo services, or no public IP | Pass `--public-ip`, or `--nat` if the machine is behind NAT. |
| `an existing K3s installation was found that this installer does not own` | K3s installed by something else | Prefer a clean host. `--force` adopts it: only with the user's agreement, knowing the installer will then manage and can uninstall it. |
| `this installer manages a dedicated single-node Cluster; N nodes were found` | Multi-node K3s | Use octelium-kubernetes-install instead. |
| `the running Cluster is not the one this installer previously managed` | K3s was reinstalled outside the installer | Investigate. `--force` accepts the new cluster and **re-bootstraps** (resource reset). |
| `<db-dir> contains data this installer did not create` (mentions migrating from the Bitnami-based installer) | Non-empty directory without the marker | Back it up. Then either choose a new `--db-dir` or, if the user accepts losing it, `--reset-db` (moves it aside). |
| `<db-dir> belongs to Octelium domain X` / `holds PostgreSQL N data` / `created for UID ...` | Marker mismatch | Use matching settings or a different `--db-dir`. Don't edit the marker. |
| `an existing PostgreSQL data directory was found but its password is not recoverable` | State dir lost, data kept | Restore `/etc/octelium/installer/postgres-password` from backup; otherwise `--reset-db` (data loss). |
| `the PersistentVolume was created with size X; resizing is not supported` | `--db-size` changed | Keep the original size. |
| `PostgreSQL/Valkey did not become ready` | Image pull, disk, SELinux, memory | Read the dumped pod events/logs: `kubectl -n default describe pod -l app.kubernetes.io/name=octelium-postgresql`. Free disk/memory, fix registry access; re-run. |
| `Valkey is answering unauthenticated commands; refusing to continue` | Valkey misconfigured | Check the `octelium-valkey` Secret/Deployment; re-run. Don't bypass. |
| `the Kubernetes API did not become ready within 15 minutes` | K3s failed to start | `journalctl -u k3s -n 200`; common causes: low memory, cgroups, conflicting firewall/CNI, missing kernel modules. |
| `could not locate the K3s CNI binary directory` | Unexpected K3s layout | Check the K3s version; pin with `--k3s-version` if a recent release changed paths. |
| Failure inside `octops init` | Cluster bootstrap problem | Inspect the bootstrap job `kubectl -n default logs job/octelium-genesis` and `kubectl -n octelium get pods`; fix the cause and re-run the installer. |

Diagnostics (read-only):

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
tail -n 200 /var/log/octelium-install.log
kubectl get nodes -o wide
kubectl get pods -A | grep -v Running
kubectl get events -A --field-selector=type=Warning --sort-by=.lastTimestamp | tail -30
kubectl -n octelium get pods,jobs
ls -l /etc/octelium/installer/        # file names only; don't print their contents
```

## Destructive options: decide deliberately

| Option | Destroys | Use only when |
| --- | --- | --- |
| `--reset-db` | Moves the current database directory to `<dir>.bak.<timestamp>`, clears bootstrap state → next bootstrap starts an empty Cluster | The directory holds data that can't be reused and the user accepts starting over. The backup directory stays on disk. |
| `--force` | Bypasses ownership/identity checks; may adopt a foreign K3s or switch domain/db-dir, clearing bootstrap state → re-bootstrap | The user understands the specific check being overridden. |
| `--uninstall` | Runs `k3s-uninstall.sh` (all K3s workloads and Kubernetes state on the host), removes installer firewall/NetworkManager changes and the kubectl symlink. Keeps database dir, state dir and CLIs. | The user wants the Cluster removed or intends a clean reinstall. |
| `--uninstall --purge-data` | Everything above plus the database directory and `/etc/octelium/installer` (credentials, initial token) | Permanent removal. Irreversible. |
| `-y` | Skips the confirmation prompt | Only after the user confirmed in the conversation, and only because there is no TTY. |

### Reinstalling means resetting Octelium's resources

`octops init` re-creates the `octelium` namespace, truncates the resource table and flushes Valkey.
So after `--uninstall` followed by a new install, the preserved database directory does **not**
keep your Users, Services, Policies, IdentityProviders or Credentials. Before a reinstall:

1. Export what should survive (needs a working login):
   `for k in ns pol idp grp usr svc cfg; do octeliumctl get $k -o yaml > backup-$k.yaml; done`
   and `octeliumctl get cc -o yaml > backup-cc.yaml`.
2. Note the Secret names (`octeliumctl get sec`); their values can't be exported and must be
   re-created.
3. After reinstall: re-create Secrets, then re-apply the exported resources (octelium-management),
   and re-issue Credentials.

### Changing an installed Cluster's network mode (`--nat`, `--public-ip`)

`--nat` only affects the Region external IP set during bootstrap, so re-running with it on an
installed Cluster changes nothing. The documented path is `--uninstall` then install with `--nat`,
which is a reset (above). The Gateway address annotation (`octelium.com/override-gw-ip`) is
refreshed on every run from `--public-ip`/detection.

### Changing domain

A different domain is a different Cluster: back up as above, `--uninstall --purge-data` (or use
another `--db-dir` and `--force`), install with the new domain, set DNS/TLS again.

## Removal checklist

1. Confirm with the user: host, Cluster domain, whether data must be kept.
2. Optional exports (above).
3. `sudo bash install-cluster.sh --uninstall` (add `--purge-data` only if asked). Without a TTY
   the prompt requires `-y`; pass it only after the user's explicit confirmation.
4. Remind the user to delete the DNS records and revoke/delete the certificate if no longer used.
5. The CLIs remain in `/usr/local/bin`; remove them if asked.
