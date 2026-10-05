# Troubleshooting a Kubernetes installation

Start with facts, not changes:

```bash
kubectl -n default get job octelium-genesis -o wide
kubectl -n default logs job/octelium-genesis --tail=200
kubectl -n octelium get pods -o wide
kubectl -n octelium get events --sort-by=.lastTimestamp | tail -40
kubectl -n octelium describe pod <pod>
kubectl -n octelium logs <pod> --all-containers --tail=200
```

| Symptom | Likely cause | What to do |
| --- | --- | --- |
| `Bootstrap validation error: ...` | Missing/empty storage fields or both/neither password forms | Fix the file (bootstrap.md). Nothing was installed. |
| `octops init` stays on "Waiting for Cluster installation to finish" | Genesis still running or failing | Read the Genesis job logs and pod events. Don't start a second init concurrently. |
| Genesis logs datastore connection/auth errors | Wrong host/port/TLS/credentials, NetworkPolicy, Secret not found | Test from a pod with `psql`/`valkey-cli` using the same values; check `passwordFromSecret` name/namespace/key. |
| Pods stuck `Pending` | No node with the required label, insufficient resources, or `gateway-init` taint that never clears | Check labels (`octelium.com/node-mode-*`), node capacity, Gateway Agent pods on data-plane nodes. |
| Service/Gateway pods fail with Multus/CNI errors (`network-attachment-definitions`, delegate not found) | Multus missing/unhealthy, Cilium exclusive, wrong CNI conf dir, missing `bridge`/`host-local` plugins | Fix Multus; `cni.exclusive=false` for Cilium; set `spec.cni.confDir`/`multusConfDir` for non-standard layouts (requires re-install: plan it); install CNI plugins. |
| `octelium-ingress-dataplane` EXTERNAL-IP `<pending>` | No load balancer implementation | Install MetalLB/kube-vip or use a cloud LB; for a single public node use `OCTELIUM_REGION_EXTERNAL_IP` at init. |
| Login: `produced zero addresses` | DNS records missing | Add `A <DOMAIN>` and `CNAME *.<DOMAIN>`. |
| Login: `x509: certificate signed by unknown authority` | Self-signed certificate still active | Install the real certificate (`cert-cluster`). |
| Login works, tunnels time out | Gateway UDP port blocked, wrong Gateway public IP | Open UDP 53820 (and 8443 for QUIC) to data-plane nodes; check `octeliumctl get gw -o yaml` `publicIPs`; set `octelium.com/override-gw-ip` on NATed nodes and restart the Gateway Agent pod on that node. |
| Front proxy: redirect loops or 404s | Proxy terminating TLS without front-proxy mode, or forwarding to the wrong port | Front proxy must forward to `octelium-ingress-dataplane.octelium.svc:8080` with `spec.ingress.frontProxy.enable: true` set at init. |
| An `octelium` namespace already exists before init | A previous installation exists | Stop: init would wipe it. Decide with the user between upgrade (octelium-cluster-ops) and a deliberate reinstall. |

A failed first attempt does not prove that the datastores are empty. Inspect the existing
namespace, Genesis Job status/logs, datastore identity and any serving resources. Continue
diagnosing the existing Job instead of launching another init. Even with no namespace, init
can reset preserved database contents: it truncates the resource table and flushes the configured
Redis DB. Re-run only for an intended reset after establishing the existing data and required
backups. After a successful install, use diagnosis or upgrade rather than init to "fix" things.

Community support: https://github.com/octelium/octelium/issues (include versions, the Genesis
logs with secrets redacted, and the Kubernetes distribution/CNI).
