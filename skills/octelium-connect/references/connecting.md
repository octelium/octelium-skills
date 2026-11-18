# Connecting with `octelium connect`

Docs: https://octelium.com/docs/octelium/latest/user/cli/connect.md

`connect` authenticates first (same rules as `login`; `--auth-token`, `--auth-token-file`,
`--assertion`, `--scope` are accepted), then brings up the tunnel. It uses IPv6-only addressing
by default when the Cluster supports it.

## Run modes

| Mode | Command | Behavior |
| --- | --- | --- |
| Detached | `octelium connect -d` (`--detach`) | Linux: runs `sudo systemd-run -p User=root -p Restart=on-failure octelium connect ...` and returns; needs sudo (may prompt for a password) and systemd. macOS: starts a background process through an administrator-privileges dialog (`osascript`), so a human must approve it. Windows: runs as a Windows service. `OCTELIUM_*` env vars are forwarded to the background process. |
| Foreground, privileged | `sudo -E octelium connect` | Blocks until Ctrl-C. `-E` keeps `OCTELIUM_DOMAIN` and the user's environment. Windows: an elevated PowerShell. |
| Foreground, rootless | `octelium connect -p svc:8080` | No TUN device or DNS changes: only published Services are reachable. |
| Stop | `octelium disconnect` | Asks the Cluster to disconnect the current Session's connection for that domain. |

Authentication happens before detaching, so a missing Session triggers the interactive
login first. In automation, provide `--auth-token-file` / `OCTELIUM_AUTH_TOKEN_FILE` (v0.51.0+),
`OCTELIUM_AUTH_TOKEN` or `--assertion`.

Since v0.51.0, Linux detached connections use a transient unit named
`octelium-connect-<domain>.service` when systemd supports `--collect` (v236+). Inspect that
unit's status and journal for startup failures; older systemd uses a generated unit name.
Stopped units are collected automatically. Use `octelium disconnect` for the intended domain
or the retained process handle for a temporary foreground connection.

## Tunnel implementation

Chosen automatically; override with `--implementation`:

| Value | Requires | Notes |
| --- | --- | --- |
| `kernel` | Linux WireGuard module (5.6+) and root or `NET_ADMIN` | Fastest. |
| `tun` | root/`NET_ADMIN` (Linux, plus `/dev/net/tun` or `MKNOD`), root on macOS, admin on Windows | wireguard-go. |
| `gvisor` | nothing | Userspace TCP/IP stack; use `-p` for local access. Serving works too, including UDP since v0.49.0. Used automatically without privileges. |

Tunnel protocol: WireGuard by default. `--tunnel-mode quicv0` (or `OCTELIUM_QUIC=true`) uses the
experimental QUIC mode, only if the Cluster enabled it.

IP mode: `--ip-mode v6` (default when available), `v4`, or `both`. Use `v4` only when an
application can't use IPv6; IPv4 ranges are more likely to collide with local networks.

## DNS

- Default: a split DNS resolver for `local.<DOMAIN>` is configured on the host (Linux uses
  `resolvectl`, so root is required; macOS uses `networksetup`). Short names like `demo-nginx`
  work because `local.<DOMAIN>` is added as a search domain.
- `--no-dns`: don't touch host DNS; use IP addresses or `-p`.
- `--localdns [--localdns-addr 127.0.0.100:53]`: run a caching DNS proxy inside the client
  (default address `127.0.0.100:53`). Recommended in containers and sidecars. It refuses `A`
  queries in IPv6-only mode (and `AAAA` in IPv4-only mode) so apps pick a reachable family.
- `--full-dns` (or `OCTELIUM_FULL_DNS=true`): send all DNS queries to the Cluster DNS; implies
  `--localdns`. It changes resolution for everything on the host, so only use it when asked.

## Publishing Services to the host (`-p`, `--publish`)

```bash
octelium connect -p myapi:8080                  # default Namespace → 127.0.0.1:8080
octelium connect -p myapi.ns1:8080              # Service in Namespace ns1
octelium connect -p svc1:8080 -p svc2:8081      # several
octelium connect -p svc:0.0.0.0:8080            # explicit bind address (exposes it to the network!)
octelium connect -p svc.ns:[::1]:9000           # IPv6 bind
```

Publishing works in every mode and is the only access path in rootless/gVisor mode. Keep the
default loopback bind unless the user explicitly wants to share the port.

Since v0.49.0, a published Service that does not exist yet is retried while the Connection
stays up and its port is published when available. Check Service existence, authorization and
client logs before treating a missing listener as a permanent startup failure.

## Serving Services from this host

A Service whose upstream sets `user: <name>` is served by that User's connected clients (for
upstreams behind NAT: laptops, private networks, IoT, remote Kubernetes). The client must opt in:

```bash
octelium connect --serve svc1                   # one Service (default Namespace)
octelium connect --serve svc1.ns1 --serve svc2  # several
octelium connect --serve-all                    # every Service assigned to this User
```

Serving works rootless too. Several connected clients serving the same Service are load
balanced (round robin). The upstream address in the Service is resolved from this host's
point of view.

## Embedded SSH and SOCKS5

```bash
octelium connect --essh                    # authorized Users can SSH into this host via the Cluster
sudo -E octelium connect --essh --essh-user ubuntu   # when running as root, force the host user
octelium connect --esocks5                 # authorized Users can proxy through this host
```

Both turn this machine into an access point for other authorized Users. Only enable them when
the user asks, and say who can use them (whoever the Cluster's Policies allow on
`essh.octelium` / `socks5.octelium` or other embedded-mode Services).

## Environment variables

| Variable | Effect |
| --- | --- |
| `OCTELIUM_DOMAIN` | Default Cluster domain. |
| `OCTELIUM_AUTH_TOKEN` / `OCTELIUM_AUTH_ASSERTION` / `OCTELIUM_ACCESS_TOKEN` | Non-interactive authentication. |
| `OCTELIUM_AUTH_TOKEN_FILE` / `OCTELIUM_ACCESS_TOKEN_FILE` | Private token file paths (v0.51.0+); see authentication.md. |
| `OCTELIUM_HOME` | State directory (profile); `mem` for in-memory. Also `--homedir`. |
| `OCTELIUM_DEV=true` | Debug logs. Verbose; review before sharing. |
| `OCTELIUM_INSECURE_TLS=true` | Skip Cluster certificate verification. Temporary, pre-certificate only. |
| `OCTELIUM_QUIC=true` | Same as `--tunnel-mode quicv0`. |
| `OCTELIUM_FULL_DNS=true` | Same as `--full-dns`. |
| `OCTELIUM_ESSH=true` / `OCTELIUM_ESOCKS5=true` | Same as `--essh` / `--esocks5`. |
| `OCTELIUM_MTU=<n>` | Override the tunnel MTU. Last resort for MTU/fragmentation problems. |
| `OCTELIUM_KEEPALIVE=<seconds>` | Override the WireGuard persistent keepalive. |
| `OCTELIUM_LOGOUT=true` | Same as the global `--logout` flag. |

## The daemon

`octelium daemon` is a privileged background service that owns credentials, connections and
host networking for one OS user and serves a local API to frontends (the CLI, the desktop app).
It is normally installed as an OS service by packages; don't start it by hand unless the user
is debugging it (`octelium daemon --help`).

Since v0.51.0, `--owner-policy login-session` is the default: the first caller normally needs an
OS login session. Root/SYSTEM callers and platforms without a usable login-session check are
accepted without one. `--owner <UID|SID>` fixes the owner explicitly;
`--owner-policy first-caller` allows the first caller without that check. Change ownership only
for the intended OS user; local API calls from other users are rejected once an owner is chosen.
