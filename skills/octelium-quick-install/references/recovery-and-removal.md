# Recovery, re-runs and removal

## How a failed run reports

On failure the installer prints the failing line and command, `full log: /var/log/octelium-install.log`,
`rerunning this script resumes from where it stopped`, then non-Running pods and recent warning
events. Datastore failures also dump the pod description and logs. Filter historical token
lines before reading logs into the transcript (commands below).

Before resuming, inspect `/etc/octelium/installer` file names and ownership, the recorded domain,
db-dir and cluster identity, the database marker, `kubectl get namespace octelium` and
`kubectl -n default get job octelium-genesis -o yaml`. Do not print password/token files or the
Bootstrap Secret. Establish what data exists and which backup meets the recovery objective.

- **Before bootstrap:** if init never ran and the configured stores are confirmed new or
  disposable, fix the cause and resume the same command.
- **Marker and namespace present:** if installer identity checks pass, re-running skips init.
  Resume with the same inputs and `OCTELIUM_SKIP_MESSAGES=true`.
- **Failure during init, missing marker or missing namespace:** re-running can invoke init,
  truncate the resource table and flush Valkey. Inspect Genesis status/logs and any serving
  resources first; a successful Job without an installer marker is not permission to reset it.
  Diagnose the existing installation/Job. Run init again only for an intended reset after
  establishing the data and backup requirements; a failed first command does not prove emptiness.

## Common errors

| Message (abridged) | Cause | Fix |
| --- | --- | --- |
| `must run as root` | Not root | `sudo env OCTELIUM_SKIP_MESSAGES=true bash install-cluster.sh ...` |
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
| Failure inside `octops init` | Cluster bootstrap problem | Inspect `kubectl -n default logs job/octelium-genesis` and `kubectl -n octelium get pods`; follow the state checks above before any re-run that could invoke init. |

Diagnostics (read-only):

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
sed '/--auth-token/d' /var/log/octelium-install.log | tail -n 200
kubectl get nodes -o wide
kubectl get pods -A | grep -v Running
kubectl get events -A --field-selector=type=Warning --sort-by=.lastTimestamp | tail -30
kubectl -n octelium get pods,jobs
ls -l /etc/octelium/installer/        # file names only; don't print their contents
```

For live progress, use `tail -n 200 -f /var/log/octelium-install.log | sed -u '/--auth-token/d'`.
Run installation/resumption with `sudo env OCTELIUM_SKIP_MESSAGES=true bash install-cluster.sh ...`.
Keep raw historical logs private; review other sensitive diagnostics locally before sharing.

## Destructive options: decide deliberately

| Option | Destroys | Use only when |
| --- | --- | --- |
| `--reset-db` | Moves the current database directory to `<dir>.bak.<timestamp>`, clears bootstrap state → next bootstrap starts an empty Cluster | The directory holds data that can't be reused and the user accepts starting over. The backup directory stays on disk. |
| `--force` | Bypasses ownership/identity checks; may adopt a foreign K3s or switch domain/db-dir, clearing bootstrap state → re-bootstrap | The user understands the specific check being overridden. |
| `--uninstall` | Runs `k3s-uninstall.sh` (all K3s workloads and Kubernetes state on the host), removes installer firewall/NetworkManager changes and the kubectl symlink. Keeps database dir, state dir and CLIs. | The user wants the Cluster removed or intends a clean reinstall. |
| `--uninstall --purge-data` | Everything above plus the database directory and `/etc/octelium/installer` (credentials, initial token) | Permanent removal. Irreversible. |
| `-y` | Skips the confirmation prompt | Only for the target and destructive outcome the user already authorized; no repeated confirmation is needed. |

### Reinstalling means resetting Octelium's resources

`octops init` re-creates the `octelium` namespace, truncates the resource table and flushes Valkey.
So after `--uninstall` followed by a new install, the preserved database directory does **not**
keep your Users, Services, Policies, IdentityProviders or Credentials. Before a reinstall:

1. Establish whether this is configuration migration or disaster recovery. Migration needs a
   working API login and the source values for Secrets. Full recovery also needs a consistent
   datastore backup, installer/Bootstrap settings, datastore credentials, TLS certificates and
   private keys, and encryption key material where applicable, with a tested restore.
2. Export applicable configuration. The management skill's `scripts/export_resources.py`
   reads every page, emits individual documents and filters system resources. If that skill is
   unavailable, use the standalone procedure below. Raw `get <kind> -o yaml` list wrappers
   cannot be reapplied, and one page is incomplete.
3. Keep the export private and validate it. Secret values and Credential tokens are not
   recoverable from the API; preserve their original sources. API configuration export also
   excludes Sessions, Devices and Authenticators and is not a datastore backup.
4. For migration after an intended reset: re-create Secrets, apply the configuration in kind
   order, re-issue Credentials and verify admin login and Service access. Review references and
   ClusterConfig if changing domains. Do not start the reset until the backups meet the objective.

### Standalone configuration export

Requires Bash and Python 3, a working `octeliumctl` login and `OCTELIUM_DOMAIN` set. This reads
every page through `listResponseMeta.hasMore`; the default is 200 items (maximum 1,000 per page).
JSON objects separated by `---` are valid YAML documents. Server-managed metadata/status is
omitted; spec references by name and Config data are preserved. Concurrent changes can make
an API export inconsistent, so coordinate configuration changes during export.

```bash
(
  set -euo pipefail
  umask 077
  export_file="$(mktemp ./octelium-config.XXXXXX.yaml)"
  trap 'rm -f "$export_file"' EXIT
  python3 - > "$export_file" <<'PY'
import json
import os
import subprocess
import sys

env = dict(os.environ)
env.pop("OCTELIUM_DEV", None)
fields = {"name", "displayName", "description", "labels", "annotations", "tags", "picURL"}

def read(*args):
    proc = subprocess.run(["octeliumctl", "get", *args, "-o", "json", "--domain", env["OCTELIUM_DOMAIN"]],
                          capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=120, check=True)
    text = proc.stdout.strip()
    result = {"items": []} if text.startswith("No ") and " found" in text else json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("expected a resource or list object")
    return result

def portable(kind, item):
    metadata = item.get("metadata") or {}
    result = {"kind": kind, "metadata": {key: value for key, value in metadata.items() if key in fields},
              "spec": item.get("spec") or {}}
    if kind == "Config" and "data" in item:
        result["data"] = item["data"]
    return result

try:
    documents = []
    for kind in ("Config", "Policy", "IdentityProvider", "Namespace", "Group", "User", "Service"):
        page = 1
        while True:
            response = read(kind.lower(), "--page", str(page))
            items = response.get("items", [])
            meta = response.get("listResponseMeta") or {}
            if not isinstance(items, list) or not isinstance(meta, dict):
                raise ValueError("invalid list response")
            for item in items:
                if not item["metadata"].get("isSystem") and not item["metadata"].get("isSystemHidden"):
                    documents.append(portable(kind, item))
            if not meta.get("hasMore"):
                break
            if not items:
                raise ValueError("empty page reports hasMore")
            page += 1
    documents.append(portable("ClusterConfig", read("cc")))
    output = "".join("---\n" + json.dumps(document) + "\n" for document in documents)
except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as err:
    print(f"export failed: {err}", file=sys.stderr)
    sys.exit(2)
sys.stdout.write(output)
PY
  trap - EXIT
  printf '%s\n' "$export_file"
)
```

### Changing an installed Cluster's network mode (`--nat`, `--public-ip`)

`--nat` only affects the Region external IP set during bootstrap, so re-running with it on an
installed Cluster changes nothing. The documented path is `--uninstall` then install with `--nat`,
which is a reset (above). The Gateway address annotation (`octelium.com/override-gw-ip`) is
refreshed on every run from `--public-ip`/detection.

### Changing domain

A different domain is a different Cluster: back up as above, `--uninstall --purge-data` (or use
another `--db-dir` and `--force`), install with the new domain, set DNS/TLS again.

## Removal checklist

1. Establish the authorized host, Cluster domain and whether data must be kept; ask only for unresolved inputs.
2. Optional exports (above).
3. `sudo bash install-cluster.sh --uninstall` (add `--purge-data` only if asked). Without a TTY
   the prompt requires `-y`; pass it only for the already-authorized removal outcome.
4. Remind the user to delete the DNS records and revoke/delete the certificate if no longer used.
5. The CLIs remain in `/usr/local/bin`; remove them if asked.
