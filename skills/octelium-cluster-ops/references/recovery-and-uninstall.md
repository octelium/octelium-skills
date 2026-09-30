# Access recovery and uninstall

## Recovering admin access

The Cluster has no superuser; API access comes only from Policies. Options, in order:

1. **Another admin** logs in and fixes the Users/Groups/Policies (octelium-management).
2. **The initial token**, if the `root-init` Credential still exists and hasn't expired (about six
   months after install). With Kubernetes access:

   ```bash
   kubectl -n octelium get secret init-token -o jsonpath='{.data.data}' | base64 -d > /secure/path/init-token
   chmod 600 /secure/path/init-token
   ```

   Quick-install hosts also keep it at `/etc/octelium/installer/init-token`. The user logs in with
   `octelium login --domain <DOMAIN> --auth-token "$(cat /secure/path/init-token)"`, repairs
   access, then deletes the file.
3. **Neither available:** there is no documented recovery command. Don't edit the PostgreSQL
   database or Octelium's Kubernetes objects by hand, and don't reinstall (that wipes everything).
   Collect the facts and ask upstream: https://github.com/octelium/octelium/issues or the
   community channels linked from https://octelium.com.

Prevention: keep at least two named admins with different IdentityProviders or a stored
break-glass Credential (short-lived, rotated), and don't delete `root-init` until they're tested.

Note on exposure: anyone who can read Secrets in the `octelium` namespace can use the initial
token while `root-init` is valid. Deleting the `root-init` Credential invalidates it.

## Uninstall

Only on explicit request. Confirm the domain and kubecontext with the user first.

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

Before any uninstall, offer an export of resources (`octeliumctl get <kind> -o yaml` per kind and
`octeliumctl get cc -o yaml`) and a database backup; Secret values can't be exported through the
API.
