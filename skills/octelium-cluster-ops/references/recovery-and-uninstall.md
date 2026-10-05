# Access recovery and uninstall

## Recovering admin access

The Cluster has no superuser; API access comes only from Policies. Options, in order:

1. **Another admin** logs in and fixes the Users/Groups/Policies (octelium-management).
2. **The initial token**, if the `root-init` Credential still exists and hasn't expired (about six
   months after install). With Kubernetes access:

   ```bash
   (
     set -euo pipefail
     umask 077
     token_file="$(mktemp /secure/path/init-token.XXXXXX)"
     trap 'rm -f "$token_file"' EXIT
     kubectl -n octelium get secret init-token -o jsonpath='{.data.data}' | base64 -d > "$token_file"
     OCTELIUM_AUTH_TOKEN="$(cat "$token_file")" octelium login --domain <DOMAIN>
   )
   ```

   The user runs this in Bash with an existing private `/secure/path` directory. Permissions
   are set before capture; producer failure stops login, and the temporary copy is removed on
   exit. Quick-install hosts also keep it at `/etc/octelium/installer/init-token`. For login from
   another machine, transfer the token privately to a mode-0600 file there, supply it through
   `OCTELIUM_AUTH_TOKEN` and remove the local copy. Don't read its contents into the transcript.
3. **Neither available:** there is no documented recovery command. Don't edit the PostgreSQL
   database or Octelium's Kubernetes objects by hand, and don't reinstall (that wipes everything).
   Collect the facts and ask upstream: https://github.com/octelium/octelium/issues or the
   community channels linked from https://octelium.com.

Prevention: keep at least two named admins with different IdentityProviders or a stored
break-glass Credential (short-lived, rotated), and don't delete `root-init` until they're tested.

Note on exposure: anyone who can read Secrets in the `octelium` namespace can use the initial
token while `root-init` is valid. Deleting the `root-init` Credential invalidates it.

## Uninstall

Only on explicit request. Establish the domain, kubecontext and data-retention requirements
from the user's authorized removal plan; ask only when one is unresolved.

| Installation | Command | Removes | Leaves |
| --- | --- | --- | --- |
| Quick installer | `sudo bash install-cluster.sh --uninstall [--purge-data]` | K3s and everything in it; installer firewall/NetworkManager changes; with `--purge-data` the database dir and `/etc/octelium/installer` | CLIs; DB and credentials unless purged (see octelium-quick-install) |
| Kubernetes (`octops init`) | `octops uninstall <DOMAIN> [--kubeconfig ...] [--kubecontext ...]` | The `octelium` namespace and everything in it | External PostgreSQL/Redis data; `default/octelium-init` Secret (contains the Bootstrap) and the `default/octelium-genesis` Job; node labels/annotations/taints; Multus/CNI; DNS records; certificates in external systems |

`octops uninstall` confirms twice in a terminal (including typing the domain) but not without a
TTY: it deletes immediately. Equivalent: `kubectl delete namespace octelium`.

Cleanup after a Kubernetes uninstall, when the user wants a clean slate:

```bash
kubectl -n default delete job octelium-genesis --ignore-not-found
kubectl -n default delete secret octelium-init --ignore-not-found       # holds the Bootstrap (datastore credentials)
kubectl label nodes --all octelium.com/node-mode-dataplane- octelium.com/node-mode-controlplane-
kubectl annotate nodes --all octelium.com/override-gw-ip-
kubectl taint nodes --all octelium.com/gateway-init- 2>/dev/null || true
```

Then, if asked: drop the PostgreSQL database and Redis data, remove DNS records, revoke
certificates, and delete the datastore credential Secrets.

Before any uninstall, establish the recovery objective and backups. For configuration migration,
use the management skill's `scripts/export_resources.py`, or the standalone paginated procedure
in the quick-install recovery reference. Read every page through `listResponseMeta.hasMore`,
extract each `.items[]` into its own document, omit system resources and server-managed
metadata/status, and export ClusterConfig separately. Raw list wrappers are not applicable
documents. Preserve name-based references and Config data; validate the stream before use.

If neither skill is installed, export each required kind with `get <kind> --page <N> -o json`,
starting at page 1, and perform that extraction/filtering until `hasMore` is false. Keep the
export in a private file. This excludes Secret values, issued Credential tokens and operational
Session/Device/Authenticator state. Full recovery needs a consistent datastore backup,
Bootstrap/installer settings, datastore credentials, certificates/private keys and encryption
key material where applicable, with a tested restore; API export alone is not disaster recovery.
