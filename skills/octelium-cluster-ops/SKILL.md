---
name: octelium-cluster-ops
description: >-
  Operate an installed Octelium Cluster at the Kubernetes/infrastructure level with octops and
  kubectl: check for and perform upgrades (`octops upgrade`), set or rotate the Cluster and
  Namespace TLS certificates (`octops cert`, cert-manager, the `cert-cluster` Secret), install or
  upgrade packages (Cordium, Enterprise), check Cluster health and component logs, add or change
  data-plane nodes and Gateway public IPs, recover the initial admin token, and uninstall
  (`octops uninstall`). Use for Day-2 operations and outages where the Cluster itself (not a
  Policy) is suspect. Not for first-time installation (octelium-quick-install,
  octelium-kubernetes-install), managing Users/Services/Policies (octelium-management), or
  client-side connection problems (octelium-connect).
license: Apache-2.0
compatibility: Requires octops and kubectl with admin access to the Kubernetes cluster running Octelium (quick-install hosts use /etc/rancher/k3s/k3s.yaml as root).
metadata:
  author: Octelium Labs, LLC
  version: "0.1.0"
  verified-against: octelium v0.43.0
---

# Octelium: Cluster operations

`octops` acts on the Kubernetes cluster that hosts Octelium (through a kubeconfig), not on the
Octelium API. Its commands take the Cluster domain as the first argument.

## Scope

- **Use for:** upgrades, certificates, packages, health checks, component logs, node and Gateway
  changes, access recovery, uninstall.
- **Hand off:** fresh installs → **octelium-quick-install** or **octelium-kubernetes-install**.
  Resource and Policy changes → **octelium-management**. Client tunnels/DNS on a user's
  machine → **octelium-connect**.

## Ground rules

Preserve the user's authorized target and outcome across steps. Prepare the concrete change
and explain its effects before executing it. Ask only for missing inputs or an unresolved change
in scope or destructive outcome; an already-authorized upgrade or rotation needs no second yes.

1. **Pick the right kubeconfig and say which.** Quick-install hosts: run as root with
   `--kubeconfig /etc/rancher/k3s/k3s.yaml` (or `KUBECONFIG=...`). Elsewhere, pass
   `--kubeconfig`/`--kubecontext` explicitly and confirm `kubectl config current-context`.
2. **No prompts without a TTY.** `octops upgrade`, `cert`, `install-package` and `uninstall` ask
   for confirmation only in a terminal; from an agent they run immediately. Check that the target
   and operation are covered by the user's request before running them.
3. **Read-only first.** Diagnose with `get`/`describe`/`logs` and `octops upgrade --check`.
   Don't delete pods, restart workloads or edit Octelium-managed Kubernetes objects to "try
   something"; Octelium reconciles its own objects, and manual edits are overwritten or break it.
4. **Never use `octops init` as a repair.** It wipes the installation (namespace, resource table,
   Redis data). Never use `octops uninstall` or `kubectl delete ns octelium` unless the user asks
   to remove the Cluster.
5. **Upgrades are one-way in practice.** Take a PostgreSQL backup before upgrading, read the
   release notes, and never downgrade with `--version` unless the release notes allow it.
6. **Certificates and keys are secrets.** Don't print private keys; show certificate metadata
   (subject, SANs, expiry) only.
7. **Don't invent** versions, domains, node names, or IPs. Read them from the cluster or ask.

## Workflow

1. **Establish access and state:** domain; kubeconfig/context; `kubectl -n octelium get pods`;
   `octops upgrade <DOMAIN> --check [--kubeconfig ...]`; `octops version`.
2. **Route to the task:**

   | Task | Reference |
   | --- | --- |
   | Upgrade the Cluster or the CLIs, package upgrades | [references/upgrade.md](references/upgrade.md) |
   | Install/rotate/inspect TLS certificates, cert-manager, Namespace certificates | [references/certificates.md](references/certificates.md) |
   | Health checks, component map, logs, Gateways, nodes, DNS/Ingress checks | [references/health-and-diagnostics.md](references/health-and-diagnostics.md) |
   | Lost admin access, initial token recovery, uninstall and cleanup | [references/recovery-and-uninstall.md](references/recovery-and-uninstall.md) |
   | Exact `octops` flags (snapshot) | [references/cli-octops.md](references/cli-octops.md) |

3. **Prepare and state the plan** (target, changes, expected downtime, rollback/backup). Proceed
   within the authorized outcome; ask before adding an unrequested destructive operation.
4. **Execute and verify:** watch the relevant pods/jobs until healthy, then test from a client
   with existing authorized access (a Service request), or ask the user to test. Reading tokens
   or starting an interactive login isn't implied by a health check.

## Quick commands

```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml            # quick-install hosts (as root)
kubectl -n octelium get pods -o wide
octops upgrade <DOMAIN> --check                         # is a newer release available?
octops upgrade <DOMAIN> --wait [--version <v>]          # upgrade and wait for Genesis
octops cert <DOMAIN> --cert fullchain.pem --key privkey.pem [--namespace <ns>]
octops install-package <DOMAIN> --package cordium|octeliumee [--upgrade] [--version <v>]
octops uninstall <DOMAIN>                                # deletes the octelium namespace only
```

## Sources of truth

1. `octops <command> --help` on the installed version.
2. Docs: https://octelium.com/docs/octelium/latest/install/cluster/upgrade.md,
   https://octelium.com/docs/octelium/latest/install/cluster/tls-certificate.md,
   https://octelium.com/docs/octelium/latest/install/cluster/uninstall.md,
   https://octelium.com/docs/octelium/latest/reference/components.md, and the llms.txt index.
3. Release notes: https://github.com/octelium/octelium/releases.
4. The bundled references.
