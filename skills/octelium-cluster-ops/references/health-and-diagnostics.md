# Health checks and diagnostics

Docs: https://octelium.com/docs/octelium/latest/reference/components.md

## Component map (namespace `octelium`)

| Component | Kubernetes workload | Role |
| --- | --- | --- |
| Ingress | `octelium-ingress`, `octelium-ingress-dataplane` (+ `LoadBalancer` Service `octelium-ingress-dataplane`) | Public HTTPS entry (API, Portal, public Services) |
| Gateway Agent | DaemonSet `octelium-gwagent` on data-plane nodes | WireGuard/QUIC tunnels; one Gateway per node |
| Nocturne | `octelium-nocturne` | Main controller: turns resources into Kubernetes workloads |
| Resource Server | `octelium-rscserver` | Storage API over PostgreSQL |
| Octovigil | `octelium-octovigil` | Authentication/authorization decisions |
| Vigil (per Service) | Deployments labeled `octelium.com/component=svc` | Identity-aware proxy of each Service, including the API server, Auth server, DNS and Portal |
| Genesis | Jobs (`default/octelium-genesis` at install, `octelium/octelium-genesis-upgrade-*` at upgrade) | Installer/upgrader |

Datastores are outside this namespace (quick install: `octelium-postgresql` StatefulSet and
`octelium-valkey` Deployment in `default`).

## Read-only health sweep

```bash
kubectl get nodes -o wide
kubectl -n octelium get pods -o wide                  # anything not Running/Ready, restart counts
kubectl -n octelium get deploy,ds,svc
kubectl -n octelium get events --sort-by=.lastTimestamp | tail -40
kubectl -n octelium get svc octelium-ingress-dataplane      # EXTERNAL-IP set
kubectl -n octelium logs deploy/octelium-nocturne --tail=200
kubectl -n octelium logs deploy/octelium-rscserver --tail=200       # datastore errors show here
kubectl -n octelium logs ds/octelium-gwagent --tail=200             # picks one pod; use -l or pod names for all
curl -sS -o /dev/null -w '%{http_code}\n' https://<DOMAIN>          # Ingress reachable (200/302/401...)
```

With an Octelium login (octeliumctl): `octeliumctl get gw -o yaml` (Gateway `status.publicIPs`,
hostname, one per data-plane node), `octeliumctl get rgn`, `octeliumctl get svc`.

## Common problems

| Symptom | Checks |
| --- | --- |
| Nobody can log in | DNS (`dig <DOMAIN>`, `dig octelium-api.<DOMAIN>`), certificate (certificates.md), Ingress pods and LB address, `octelium-rscserver` logs for datastore errors. |
| Logins work, tunnels don't | UDP 53820 (and 8443 QUIC) reachable on data-plane nodes; Gateway `publicIPs` correct; `octelium-gwagent` logs; NAT → `octelium.com/override-gw-ip`. |
| One Service down | Its Vigil pods (`kubectl -n octelium get pods -l octelium.com/component=svc -o wide`, find by name), upstream reachability, managed-container logs. Policy denials are not an ops problem (octelium-management). |
| Pods Pending | Node labels, capacity, `octelium.com/gateway-init` taint stuck (Gateway Agent not ready on that node). |
| Datastore outage | PostgreSQL/Redis health and credentials; components recover when the stores return. |
| Disk pressure on quick-install hosts | `df -h /var/lib/rancher /mnt/octelium/db`; image garbage collection; PV size is fixed at install. |

## Node and Gateway changes

- **Add a data-plane node:** join it to Kubernetes, `kubectl label node <n> octelium.com/node-mode-dataplane=`,
  annotate `octelium.com/override-gw-ip=<PUBLIC_IP>` if NATed, open UDP ports. The Cluster
  taints it with `octelium.com/gateway-init` until its Gateway Agent is ready (v0.39.0+) and
  creates a Gateway.
- **Remove a node:** drain it (`kubectl drain`), then remove it; clients reconnect to other
  Gateways. Check Services with `deployment.replicas` > 1 for capacity.
- **Change a Gateway's public IP:** update the annotation, restart that node's Gateway Agent pod,
  and update any QUIC Gateway DNS records.
- **Quick-install hosts:** single node by design; re-running the installer refreshes the
  `override-gw-ip` annotation from `--public-ip`/detection.

## Access logs and metrics

Services emit OpenTelemetry logs/metrics to `octelium-collector.octelium.svc:8080` (OTLP gRPC).
Deploy a collector there (see the visibility docs) to get per-request `ALLOWED`/`DENIED` records.
