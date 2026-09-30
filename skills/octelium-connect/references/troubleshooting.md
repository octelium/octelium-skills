# Client troubleshooting

Always capture the exact error text first. Re-run the failing command with `OCTELIUM_DEV=true`
for debug logs when the error is unclear (review the output before sharing it).

## Login / API errors

| Symptom | Cause | Action |
| --- | --- | --- |
| `name resolver error: produced zero addresses` | Cluster DNS records missing or not yet propagated | Check `getent hosts <DOMAIN>` and `getent hosts octelium-api.<DOMAIN>` (or `dig`/`nslookup`). Both must resolve: an `A` record for `<DOMAIN>` and a wildcard `*.<DOMAIN>`. Flush the local DNS cache (`sudo resolvectl flush-caches`; macOS `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`; Windows `ipconfig /flushdns`). Missing records are a Cluster admin task. |
| `x509: certificate signed by unknown authority` / `authentication handshake failed` | Cluster still uses its initial self-signed certificate, or the cert expired | Admin must install the real certificate (octelium-cluster-ops). Temporary: `OCTELIUM_INSECURE_TLS=true` for that one command, and tell the user it disables verification. |
| `connection refused` / `Unavailable` dialing `:443` | Ingress not reachable: firewall, wrong IP in DNS, ingress without external IP | Cluster-side issue; `curl -k https://<DOMAIN>` should return the login page HTML. Hand off with details. |
| Command hangs with "Waiting for you to approve the login in your browser" | No Session; web login started | Stop it. Ask the user to log in themselves, or use a token/assertion. |
| `You must choose the authentication type ...` | Headless container/CI host without a Session | Provide `--auth-token`/`OCTELIUM_AUTH_TOKEN` or `--assertion`. |
| `Cannot use login command in proxy mode` | `OCTELIUM_AUTH_PROXY_SOCKET` is set | Already authenticated; skip login. |
| `PermissionDenied` / `Unauthorized` on API calls (`octeliumctl get ...`) | Session is valid but Policies don't allow that API | Expected for non-admins. Don't try to work around it; an admin decides. |
| Session `PENDING`/`REJECTED` | Cluster requires approval | Admin: `octeliumctl update session --approve <name>`. |

## Tunnel problems

| Symptom | Checks |
| --- | --- |
| `connect -d` fails immediately | Linux needs `sudo` + systemd (`systemd-run`); macOS shows an admin dialog. Without them, run the foreground command in a background process or use rootless `-p`. |
| Connected but no interface / only `-p` works | Running unprivileged → gVisor mode. Use `sudo -E octelium connect`, or `NET_ADMIN` in containers. |
| Connects, but every Service times out | UDP egress to the Gateway blocked (WireGuard port, default `53820/udp`), or a NATed Cluster installed without `--nat`. Compare with the browser Portal at `https://portal.<DOMAIN>`: if public access works but tunnels don't, it's Cluster networking (octelium-cluster-ops). |
| Works on one network, not another | Corporate firewall blocking UDP; try `--tunnel-mode quicv0` only if the Cluster enabled QUIC. |
| Large transfers stall, small requests work | MTU/fragmentation. Try `OCTELIUM_MTU=1200` (or lower) as a diagnostic, not a default. |
| Connection drops behind NAT when idle | Try `OCTELIUM_KEEPALIVE=25`. |
| IPv4-only application can't reach Services | Default is IPv6-only; use `--ip-mode both` or `v4`, or `--localdns` so the app gets the reachable family. |

## Name resolution

Tunnel up but `Could not resolve host: <svc>`:

1. Bypass DNS: `octelium connect -p <svc>:9000` then `curl localhost:9000`. If this works, the
   problem is host DNS integration.
2. Try the FQDN `<svc>.local.<DOMAIN>` (or `<svc>.<ns>.local.<DOMAIN>`); short names rely on
   the search domain.
3. Linux: DNS setup uses `resolvectl` and needs root; unprivileged connects don't touch DNS.
   Check `resolvectl status` for `local.<DOMAIN>`.
4. Containers/sidecars can't have their `/etc/resolv.conf` updated by another container; use
   `--localdns` and point the app at `127.0.0.100`, or use `-p`.
5. VPN or DNS software (another VPN, dnsmasq, Pi-hole) may override split DNS.

## Reaching the Service fails after DNS works

- HTTP 403 / connection reset right after connecting → authorization. The User lacks a Policy
  that allows this Service. Report which User, Service, and request; an admin decides
  (octelium-management). Don't suggest `allow-all` as a fix.
- 502/503/timeouts → upstream unreachable from where it is served (the Cluster, or a serving
  User's host that isn't connected with `--serve`). `octelium get svc <name> -o yaml`
  shows the upstream; checking health is an admin task.
- `--serve` running but Users can't reach it → the serving client must be connected as the
  User named in `upstream.user`, the upstream address must be reachable from that host, and
  the Service name passed to `--serve` must match (`svc.ns` for non-default Namespaces).
- eSSH `Permission denied` → wrong SSH user (must be the target Session name), the target isn't
  connected with `--essh`, or Policies deny it.

## What to collect before escalating

`octelium version`, OS/arch, how it was run (root, container, flags), exact error text,
`OCTELIUM_DEV=true` logs around the failure (redact tokens), `octelium status -o yaml` (redact),
and whether browser access to `https://<DOMAIN>` works. Community support: GitHub issues at
https://github.com/octelium/octelium/issues.
