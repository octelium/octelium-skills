# Upgrades

Docs: https://octelium.com/docs/octelium/latest/install/cluster/upgrade.md

## Cluster upgrade

```bash
octops upgrade <DOMAIN> --check [--kubeconfig <path>] [--kubecontext <ctx>]   # compare with latest release
octops upgrade <DOMAIN> [--version <v>] [--wait] [--kubeconfig ...]         # default version: latest
```

- Upgrade runs a Genesis job `octelium-genesis-upgrade-<random>` in the `octelium` namespace
  that updates the components. Without `--wait`, `octops` returns as soon as the job starts;
  prefer `--wait`, or follow `kubectl -n octelium logs -f job/<name>`.
- It does not reset data (unlike `octops init`).
- Quick-install hosts: `KUBECONFIG=/etc/rancher/k3s/k3s.yaml`; re-running the installer with a
  new `--version` is **not** an upgrade.

### Before

1. `octops upgrade <DOMAIN> --check`; read the release notes between the current and target
   versions (https://github.com/octelium/octelium/releases) for breaking changes.
2. Back up PostgreSQL (managed snapshot, `pg_dump`, or the quick-install dump command) and keep
   the Bootstrap/credentials. The backup contains Secret values: store it encrypted.
3. Upgrade the `octops` CLI first so it knows the target version
   (`curl -fsSL https://octelium.com/install.sh | bash`, or `VERSION=vX.Y.Z` to pin).
4. Check health now (health-and-diagnostics.md) so pre-existing problems aren't blamed on the
   upgrade.
5. **Clusters installed before v0.40.0** with `OCTELIUM_FRONT_PROXY_MODE`,
   `OCTELIUM_ENABLE_SPIFFE_CSI` (or other SPIFFE variables) or `OCTELIUM_CNI_CONF_DIR`: v0.40.0+
   reads these settings from the installation config captured by `octops init`, not from the
   environment, and older Clusters don't have that config. Verify how the target release handles
   such a Cluster (release notes, a staging Cluster, or upstream support) before upgrading
   production. For older targets, the docs' rule applies: export the same variables for every
   `octops upgrade`.
6. Agree on a window: Services and tunnels can blip while components roll.

### After

```bash
kubectl -n octelium get jobs | grep genesis-upgrade
kubectl -n octelium get pods               # all Running/Ready, recent restarts explained
octops upgrade <DOMAIN> --check            # reports up to date
```

Then log in and connect from a client, and test one Service of each important mode.

If the upgrade job fails: collect its logs (`kubectl -n octelium logs job/<name>`), don't retry in a
loop, don't run `init`; fix the reported cause (often image pulls or node resources) and re-run
`octops upgrade`, or escalate with the logs.

## CLI upgrades

```bash
octelium version --check            # same for octeliumctl / octops
curl -fsSL https://octelium.com/install.sh | bash          # Linux/macOS
iwr https://octelium.com/install.ps1 -useb | iex           # Windows
brew upgrade octelium/tap/octelium                          # Homebrew installs
```

Keep client CLIs reasonably close to the Cluster version; a CLI older than the Cluster may warn
about and drop newer resource fields during `octeliumctl apply`.

## Packages

```bash
octops install-package <DOMAIN> --package cordium       # or octeliumee (Enterprise)
octops install-package <DOMAIN> --package cordium --upgrade [--version <v>]
```

Quick-install hosts can also pass `--cordium`/`--enterprise` at install time. The Enterprise
package is free for personal and evaluation use; production licensing is the user's call.
