---
name: octelium-kubernetes-install
description: >-
  Plan and perform a production Octelium Cluster installation on an existing Kubernetes cluster
  (EKS, GKE, AKS, DigitalOcean, Linode, on-prem, k3s/RKE2/Talos, multi-node) with `octops init`
  and a Bootstrap file. Covers Octelium data-plane/control-plane node labels, primary CNI plus
  Multus (Cilium non-exclusive), CNI conf dir, Gateway public IPs and the
  `octelium.com/override-gw-ip` annotation, the LoadBalancer Ingress, front proxy mode, SPIFFE,
  external PostgreSQL and Redis/Valkey with passwordFromSecret, network ranges, QUIC, and
  post-install DNS, TLS (cert-manager or `octops cert`) and first login. Use for "install
  Octelium on Kubernetes/production/multi-node" or `octops init` problems. Not for a single fresh
  VM (octelium-quick-install), upgrades or Day-2 operations (octelium-cluster-ops), or managing
  resources (octelium-management).
license: Apache-2.0
compatibility: Requires kubectl and octops with cluster-admin access to the target Kubernetes cluster, reachable PostgreSQL and Redis-compatible datastores, and a domain the user controls.
metadata:
  author: Octelium Labs, LLC
  version: "0.1.0"
  verified-against: octelium v0.43.0
---

# Octelium: production install on Kubernetes

`octops init <DOMAIN> --bootstrap <file>` installs Octelium into the `octelium` namespace of an
existing Kubernetes cluster by running the Genesis installer job, then waits for the Cluster and
prints the initial login token. Everything else (nodes, CNI, datastores, load balancer, DNS,
certificates) is the operator's responsibility and must be ready or planned first.

## Scope

- **Use for:** production and multi-node installations, bring-your-own Kubernetes/datastores,
  Bootstrap authoring, `octops init` failures.
- **Hand off:** one fresh VM → **octelium-quick-install**. Upgrades, certificate rotation,
  packages, health, uninstall → **octelium-cluster-ops**. Users/Services/Policies →
  **octelium-management**.

## Ground rules

1. **`octops init` is destructive for an existing installation.** It deletes and re-creates the
   `octelium` namespace, and Genesis truncates the `octelium_resources` table and flushes the
   Redis database it's given. Never run it against a Kubernetes cluster that already has an
   `octelium` namespace, or with datastores holding another Cluster's data, unless the user asks
   to wipe and re-create. It isn't a repair or upgrade tool.
2. **No confirmation without a TTY.** `octops init` normally asks for confirmation; from an agent
   shell it proceeds immediately. Get the user's explicit go-ahead for the exact command,
   kubecontext and domain first.
3. **Dedicated datastores.** Use a dedicated PostgreSQL database and a dedicated Redis/Valkey
   (or at least a dedicated DB index): Genesis flushes the Redis DB. Never point it at a shared
   cache.
4. **Keep credentials out of the Bootstrap file.** Prefer `passwordFromSecret` (Kubernetes
   Secret references) over inline passwords; `octops init` stores the whole Bootstrap in the
   `default/octelium-init` Kubernetes Secret, and files end up in shells, repos and backups.
   Never invent datastore hosts or credentials: ask.
5. **Keep the initial token out of logs.** Run init with
   `OCTELIUM_AUTH_TOKEN_SAVE_PATH=<private file>` (written with mode 0600) and
   `OCTELIUM_SKIP_MESSAGES=true` so the token isn't printed into the terminal or transcript.
6. **Don't guess network facts.** Node public IPs, NAT, load balancer type, CNI and container
   runtime come from the cluster (`kubectl get nodes -o wide`, provider docs) or the user.
   Changing the Cluster network range after installation isn't supported by these tools: check
   `100.64.0.0/10` (the default IPv4 range) against the user's networks before install.
7. **Target the right cluster.** Pass `--kubeconfig`/`--kubecontext` explicitly and echo
   `kubectl config current-context` back to the user before installing.

## Workflow

1. **Discover** (read-only): `kubectl version`, `kubectl get nodes -o wide --show-labels`,
   CNI pods (`kubectl get pods -n kube-system`), container runtime (node `CONTAINER-RUNTIME`
   column), `kubectl get ns octelium` (must be NotFound), `kubectl get storageclass`, whether a
   `LoadBalancer` Service gets an external IP on this cluster.
2. **Plan with the user** using references/prerequisites.md: which nodes are Octelium
   data-plane (Gateways, need public reachability on UDP 53820) and control-plane (at least one
   each; 2 vCPU/2 GB per node minimum); Multus install flavor; CNI conf dir; datastores;
   Ingress exposure (cloud LB, MetalLB, or single-node external IP); front proxy; SPIFFE;
   network mode/range; QUIC; target Octelium version.
3. **Prepare the cluster:** label nodes (`octelium.com/node-mode-dataplane=` /
   `octelium.com/node-mode-controlplane=`), annotate NATed data-plane nodes with
   `octelium.com/override-gw-ip=<PUBLIC_IP>`, install/verify the CNI and Multus, create datastore
   credential Secrets.
4. **Write the Bootstrap** (references/bootstrap.md; template `assets/bootstrap.example.yaml`).
5. **Check datastore connectivity from inside the cluster** (a throwaway pod with `psql`/
   `valkey-cli` or `redis-cli` against the exact host/port/TLS settings) before init.
6. **Install** (after explicit confirmation):
   ```bash
   (
     set -euo pipefail
     umask 077
     token_file="$(mktemp ./octelium-init-token.XXXXXX)"
     printf '%s\n' "$token_file"
     OCTELIUM_AUTH_TOKEN_SAVE_PATH="$token_file" OCTELIUM_SKIP_MESSAGES=true \
       octops init <DOMAIN> --bootstrap bootstrap.yaml --kubeconfig <path> --kubecontext <ctx> [--version <v>]
   )
   ```
   Report the protected token path only. On failure, retain the file privately for diagnosis;
   the command may have saved a token before a later failure. It blocks until the Cluster is
   ready (often several minutes). Run with a long timeout or in
   the background; follow `kubectl -n default logs -f job/octelium-genesis`.
7. **Verify, DNS, TLS, first login** → references/install-and-verify.md: pods Ready in
   `octelium`, `octelium-ingress-dataplane` has an external address, DNS `A <DOMAIN>` +
   `CNAME *.<DOMAIN>`, certificate Secret `cert-cluster`, then the user logs in with the saved
   token and creates named admins (octelium-management).

## References

| Need | File |
| --- | --- |
| Node roles, CNI/Multus, Cilium, CNI dirs, Gateways and NAT, Ingress/LB, front proxy, SPIFFE, ports, datastores | [references/prerequisites.md](references/prerequisites.md) |
| Bootstrap fields, examples, secrets, version differences | [references/bootstrap.md](references/bootstrap.md) |
| `octops init` behavior and env vars, verification, DNS, TLS, first login | [references/install-and-verify.md](references/install-and-verify.md) |
| Failure symptoms and fixes | [references/troubleshooting.md](references/troubleshooting.md) |
| Exact `octops` flags (snapshot) | [references/cli-octops.md](references/cli-octops.md) |

## Sources of truth

1. `octops <command> --help` of the installed version (and the version you install: pass
   `--version` to pin).
2. Docs: https://octelium.com/docs/octelium/latest/install/cluster/pre-install.md,
   https://octelium.com/docs/octelium/latest/install/cluster/installing-cluster.md,
   https://octelium.com/docs/octelium/latest/install/cluster/bootstrap.md, and the llms.txt index.
   Where the docs describe environment variables that this skill says moved into the Bootstrap
   (v0.40.0+), trust the Bootstrap for v0.40.0 and later.
3. The bundled references.
