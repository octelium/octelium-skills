# Accessing Services

Docs: https://octelium.com/docs/octelium/latest/user/cli/access.md

## Discover what exists

```bash
octelium get svc                     # Services visible to you (alias: service, services)
octelium get svc -n production       # filter by Namespace
octelium get svc -o yaml             # full detail (-o json for jq)
octelium get ns                      # Namespaces
octelium get svc --order-by-name --items-per-page 50 --page 2
```

The table shows NAME, NAMESPACE, PORT, TYPE (mode), ADDRESSES (private IPv4/IPv6), TLS and
PUBLIC. Use these values; don't guess ports or modes.

## Addressing

| Service | Private names (client-based, while connected) | Public URL (only if PUBLIC is true) |
| --- | --- | --- |
| `web` in `default` | `web`, `web.local.<DOMAIN>`, `web.default.local.<DOMAIN>` | `https://web.<DOMAIN>` |
| `web` in `prod` | `web.prod` (short name), `web.prod.local.<DOMAIN>` (preferred) | `https://web.prod.<DOMAIN>` |
| `default` in `prod` | also `prod.local.<DOMAIN>` | `https://prod.<DOMAIN>` |

- Short names depend on the DNS search domain the client configures; use the full FQDN in
  scripts and when a short name doesn't resolve.
- Without DNS (`--no-dns`) use the addresses from `octelium get svc`, e.g.
  `curl 'http://[fdee:e801::17]'` (IPv6 is the default tunnel family).
- With `-p svc:port`, use `localhost:<port>` instead of the Service name.
- TLS-enabled Services (TLS column set) must be addressed by FQDN over TLS, e.g.
  `https://nginx.local.<DOMAIN>`.

## Protocol clients

Use the standard client for the Service's mode. Upstream credentials are usually injected by
the Cluster ("secretless" access), so don't ask the user for upstream passwords or keys unless
access fails with an upstream authentication error.

| Mode | Example |
| --- | --- |
| `HTTP` / `WEB` / `GRPC` | `curl http://demo-nginx`, `grpcurl ...` against the Service host/port |
| `SSH` | `ssh ssh-h01`, or `ssh -p 2022 ssh-h01` for a non-default port |
| `POSTGRES` | `psql -h my-postgres-db-1` (user/database may be forced by the Service) |
| `MYSQL` | `mysql -h mysql-db-1 [-P 3456]` with an empty password |
| `KUBERNETES` | `octelium config k8s-01` (alias `cfg`), then `export KUBECONFIG=<printed path>`; `kubectl ...` |
| `SOCKS5` | `curl --socks5 socks5-svc:1080 https://example.org` |
| `DNS`, `TCP`, `UDP` | Point the ordinary client at the Service host/port |
| `MCP`, `LLM` | Usually public Services used over HTTPS with a bearer token (see clientless below) |

`octelium config <svc>[.<ns>]` writes a kubeconfig for a `KUBERNETES` Service under
`~/.kube/` and prints the `KUBECONFIG` path to export.

## Embedded SSH / SOCKS5 into a connected Session's host

A host that runs `octelium connect --essh` can be reached through the built-in `essh.octelium`
Service (or any Service with `eSSHMode`), using the target **Session name** as the SSH user:

```bash
octeliumctl get sess                         # find the connected Session, e.g. usr1-9o2ztp
ssh usr1-9o2ztp@essh.octelium                # standard OpenSSH client
octelium ssh usr1-9o2ztp                     # built-in client: interactive shell
octelium ssh usr1-9o2ztp -- uptime           # remote command after --
octelium ssh usr1-9o2ztp -N -L 5432:localhost:5432   # local port forward, no shell
octelium ssh usr1-9o2ztp -D 1080 -N          # dynamic SOCKS5 forward
octelium cp ./file.json usr1-9o2ztp:/home/user/file.json
octelium cp -r usr1-9o2ztp:/home/user/dist/ ./dist/
octelium cp sessA:/data.json sessB:/data.json      # session to session
```

Listing Sessions needs `octeliumctl` and a Policy that allows it. The caller must be connected
(or reach the Cluster otherwise) and be authorized by the Cluster's Policies.

For a host running `--esocks5`, the SOCKS5 username is the Session name:
`curl --socks5 usr1-9o2ztp@socks5.octelium:1080 https://checkip.amazonaws.com`; traffic exits
from that host.

## Clientless access (no tunnel)

Only for Services with PUBLIC set (`isPublic: true`; modes `HTTP`, `WEB`, `GRPC`, `KUBERNETES`,
and the HTTP-based `MCP`/`LLM` modes):

- **Humans:** open `https://<svc>.<DOMAIN>` (or `https://<svc>.<ns>.<DOMAIN>`) in a browser and
  log in through the Cluster's IdentityProviders. The Portal is at `https://portal.<DOMAIN>`.
- **Workloads, OAuth2 client credentials:** the admin creates
  `octeliumctl create cred --type oauth2 --user <workload-user>`; the app posts
  `grant_type=client_credentials`, `client_id`, `client_secret` (form body) to
  `https://<DOMAIN>/oauth2/token` and sends `Authorization: Bearer <access_token>` (or
  `X-Octelium-Auth: <token>`). Standard OAuth2 libraries handle renewal.
- **Workloads, static access token:** `octeliumctl create cred --type access-token --user <u>`;
  use it directly as a bearer token. It is not renewed automatically.
- **Go:** the `octelium-go` SDK (https://octelium.com/docs/octelium/latest/management/guide/sdk.md).

Docs: https://octelium.com/docs/octelium/latest/user/clientless/oauth2.md
