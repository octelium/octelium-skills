# Prerequisites for installing on Kubernetes

Docs: https://octelium.com/docs/octelium/latest/install/cluster/pre-install.md

## Kubernetes and nodes

- Any conformant Kubernetes (managed or self-hosted), amd64 or arm64 nodes (Cluster images
  support both since v0.27.0).
- Octelium uses the `octelium` namespace (created by init; an existing one is deleted).
- **Node roles** (independent of Kubernetes' own control plane; an Octelium control-plane node is
  an ordinary worker):

  ```bash
  kubectl label nodes <node> octelium.com/node-mode-dataplane=      # Gateways + Service proxies + managed containers
  kubectl label nodes <node> octelium.com/node-mode-controlplane=   # Octelium control-plane components
  ```

  Production: at least one of each on separate nodes, 2 vCPU / 2 GB RAM or more per node; scale
  data-plane nodes with traffic. A node may carry both labels in small setups.
- **Gateway-init taint:** since v0.39.0 Genesis and the node controller add
  `octelium.com/gateway-init=true:NoSchedule` to dedicated data-plane nodes until their Gateway
  Agent is ready, including nodes added later by autoscalers. The manual
  `kubectl taint nodes <node> octelium.com/gateway-init=true:NoSchedule` from older docs is
  harmless but no longer needed.

## Gateways and public reachability

Every data-plane node is a Gateway terminating WireGuard (UDP `53820` by default, configurable in
the Bootstrap) and, if enabled, QUIC (UDP `8443`). Clients connect to the node's public address
directly, so:

- data-plane nodes need a public IP reachable on those UDP ports (security groups/firewalls);
- behind NAT or with several addresses, set the public IP explicitly:
  `kubectl annotate node <node> octelium.com/override-gw-ip=<PUBLIC_IP>`; otherwise the
  Gateway Agent detects it at startup;
- the WireGuard kernel module on data-plane nodes is recommended (fallback: wireguard-go);
- clients need only outbound access.

## CNI and Multus

- A primary CNI is required (Cilium, Calico, cloud CNIs, ...).
- Multus is required. Install the variant matching the container runtime:

  ```bash
  # containerd (most clusters)
  kubectl apply -f https://raw.githubusercontent.com/k8snetworkplumbingwg/multus-cni/master/deployments/multus-daemonset.yml
  # CRI-O
  kubectl apply -f https://raw.githubusercontent.com/k8snetworkplumbingwg/multus-cni/master/deployments/multus-daemonset-crio.yml
  ```

  Those manifests track `master`; for production pin a released tag of multus-cni instead, and
  prefer the provider's supported Multus add-on where one exists.
- **Cilium** must run as a non-exclusive CNI: `cilium install ... --set cni.exclusive=false`
  (or the equivalent Helm value), otherwise it removes Multus' configuration.
- The standard `bridge` and `host-local` CNI plugins must exist in the CNI bin directory (usually
  `/opt/cni/bin`; managed clusters normally ship them).
- **CNI configuration directory:** the Gateway Agent writes Multus delegate configuration to
  `/etc/cni/multus/net.d` by default. For distributions with other paths (e.g. k3s:
  `/var/lib/rancher/k3s/agent/etc/cni`), set it in the Bootstrap (v0.40.0+):
  `spec.cni.confDir` (Multus dir becomes `<confDir>/multus/net.d`) or `spec.cni.multusConfDir`
  (explicit). Releases before v0.40.0 used the `OCTELIUM_CNI_CONF_DIR` environment variable of
  `octops init`.

## Ingress (public HTTPS entry)

- Genesis creates the `LoadBalancer` Service `octelium-ingress-dataplane` (TCP 443) in `octelium`.
  Managed Kubernetes provisions a cloud load balancer automatically.
- Bare metal: provide a load-balancer implementation (MetalLB, kube-vip, Cilium LB-IPAM, ...),
  or for a single public node set `OCTELIUM_REGION_EXTERNAL_IP=<public IP>` when running
  `octops init` to use that address as the external IP.
- **Front proxy:** to terminate TLS on an external L7 proxy/load balancer that forwards to
  `octelium-ingress-dataplane.octelium.svc:8080`, set `spec.ingress.frontProxy.enable: true` in
  the Bootstrap (v0.40.0+; persisted across upgrades). Releases before v0.40.0 used
  `OCTELIUM_FRONT_PROXY_MODE=true` on `octops init` **and every** `octops upgrade`.
  Only enable `useForwardedForHeader` in ClusterConfig when such a trusted proxy is in front.

## SPIFFE (optional)

Cluster components can authenticate each other with X.509-SVIDs from an existing SPIRE
deployment (CSI driver, default `csi.spiffe.io`). v0.40.0+: Bootstrap
`spec.spiffe.enable: true`, optional `trustDomain` and `csiDriver.name`. Before v0.40.0:
`OCTELIUM_ENABLE_SPIFFE_CSI=true`, `OCTELIUM_SPIFFE_CSI_DRIVER`, `OCTELIUM_SPIFFE_TRUST_DOMAIN` on
`octops init` and every `octops upgrade`. SPIRE must already run in the cluster.

## Datastores

| Store | Purpose | Requirements |
| --- | --- | --- |
| PostgreSQL | Primary store for all resources | Dedicated database; user able to create tables in it; reachable from pods; TLS (`isTLS`) recommended for anything outside the cluster |
| Redis-compatible (Redis, Valkey, managed Redis) | Cache and pub/sub between components | Dedicated instance or DB index (Genesis flushes it at init); AUTH password; TLS as needed |

Managed services (RDS/Cloud SQL/Azure Database, ElastiCache/Memorystore) or in-cluster
operators (CloudNativePG, Valkey/Redis charts) all work. Plan backups (the PostgreSQL database is
the Cluster's state, including Secrets in plaintext unless you add encryption at rest).

## Network ranges

Private addresses for Services and connected clients come from the Cluster network: dual-stack by
default, IPv4 `100.64.0.0/10`, IPv6 a random `fd00::/8` range. Override in the Bootstrap only
after checking for overlap with client and site networks; `V6_ONLY` avoids IPv4 collisions
entirely. Decide before installing.

## Checklist

- [ ] kubecontext confirmed; no existing `octelium` namespace
- [ ] data-plane and control-plane labels set; UDP 53820 (and 8443 for QUIC) open to data-plane nodes
- [ ] `override-gw-ip` on NATed/multi-IP data-plane nodes
- [ ] CNI + Multus healthy (Cilium non-exclusive); CNI conf dir known
- [ ] `LoadBalancer` works (or external IP plan / front proxy plan)
- [ ] PostgreSQL + Redis reachable from pods, dedicated, credentials in Kubernetes Secrets
- [ ] domain chosen, DNS access, certificate plan (cert-manager recommended)
- [ ] Octelium version chosen (`--version`, default `latest`)
