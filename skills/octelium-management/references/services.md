# Services

Docs: https://octelium.com/docs/octelium/latest/management/core/service/overview.md
Schema: https://octelium.com/schemas/octelium/latest/core.v1.Service.schema.json

A Service is an identity-aware proxy (Vigil) in front of one upstream. It decides access per
request with Policies, can inject upstream credentials ("secretless"), and logs L7 details.

## Top-level spec fields

| Field | Meaning |
| --- | --- |
| `mode` | Protocol: `HTTP`, `WEB`, `GRPC`, `KUBERNETES`, `SSH`, `POSTGRES`, `MYSQL`, `TCP`, `UDP`, `DNS`, `SOCKS5`, `RDP`, `RDP_WEB`, `MCP`, `LLM` |
| `port` | Port the Service listens on (inferred from the upstream URL when omitted) |
| `config` | Default configuration: `upstream`, mode block (`http`, `ssh`, `postgres`, `mysql`, `kubernetes`, `socks5`, `rdp`, `mcp`, `llm`), `tls` (upstream TLS client) |
| `dynamicConfig` | Named alternative configs + rules choosing one per request |
| `authorization` | `policies` / `inlinePolicies` (see policies.md) |
| `isPublic` | Also expose publicly through the Ingress at `https://<svc>.<ns>.<DOMAIN>` (HTTP-based modes); authentication still required |
| `isAnonymous` | With `isPublic`: no authentication at all (public websites/APIs) |
| `isTLS` | Listen over TLS for client-based access (needs the Namespace wildcard certificate) |
| `isDisabled` | Stop serving new requests without deleting |
| `deployment.replicas` | Proxy replicas |
| `region` | Region to deploy in (multi-Region Clusters) |
| `attrs` | Data for Policies |

Pick the mode for the protocol; use `WEB` (not `HTTP`) for browser apps so the Portal shows them,
and `TCP`/`UDP` only when no L7 mode fits.

## Upstreams

```yaml fragment
config:
  upstream:
    url: https://api.internal.example.com          # reachable from the Cluster
```

```yaml fragment
config:
  upstream:
    url: postgres://db.home.lan:5432               # resolved on the serving User's host
    user: homelab-connector                         # served by `octelium connect --serve <svc>`
```

```yaml fragment
config:
  upstream:
    loadbalance:
      endpoints:
        - url: https://backend1.example.com
        - url: https://backend2.example.com
```

```yaml fragment
config:
  upstream:
    container:                                      # managed container on data-plane nodes
      image: nginx:latest
      port: 80
      replicas: 2
      env:
        - name: MODE
          value: production
```

`https://`/`tls://` upstreams use TLS; `config.tls` sets `trustedCAs`, `appendToSystemPool`,
`insecureSkipVerify` and `clientCertificate.fromSecret` for mTLS. Managed containers also support
secret env vars, private registries, resources, volumes and probes (docs:
https://octelium.com/docs/octelium/latest/management/core/service/managed-containers.md).

## Secretless upstream credentials

Create the Secret first (the user types the value; see secrets-and-cluster-config.md), then
reference it by name.

HTTP bearer token:

```yaml
kind: Service
metadata:
  name: openai-api
spec:
  mode: HTTP
  config:
    upstream:
      url: https://api.openai.com
    http:
      auth:
        bearer:
          fromSecret: openai-api-key
```

SSH with a private key and pinned host key:

```yaml
kind: Service
metadata:
  name: ssh1
spec:
  mode: SSH
  port: 22
  config:
    upstream:
      url: ssh://10.0.0.5
    ssh:
      user: ubuntu
      auth:
        privateKey:
          fromSecret: ssh1-private-key
      upstreamHostKey:
        key: ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleOnlyReplaceMe
```

PostgreSQL with a forced user and database:

```yaml
kind: Service
metadata:
  name: pg-db
spec:
  mode: POSTGRES
  port: 5432
  config:
    upstream:
      url: postgres://pg.internal.example.com
    postgres:
      user: app_readonly
      database: app
      auth:
        password:
          fromSecret: pg-password
      sslMode: VERIFY_FULL
```

`VERIFY_FULL` verifies the certificate chain and the hostname in the upstream URL. Use the
server's certified DNS name. For a private CA, add its PEM certificate under the same config:

```yaml fragment
tls:
  trustedCAs:
    - <PEM_CA_CERTIFICATE>
```

System CAs are used by default. `REQUIRE` encrypts without verifying the server certificate;
choose it only as an explicit environment decision. PostgreSQL statement Policies also need
`config.postgres.authorization.mode: ALL`; by default authorization runs at connection setup
(policies.md).

Kubernetes API with a kubeconfig stored as a Secret:

```yaml
kind: Service
metadata:
  name: k8s-prod
spec:
  mode: KUBERNETES
  config:
    upstream:
      url: https://k8s.example.com:6443
    kubernetes:
      kubeconfig:
        fromSecret: kubeconfig-k8s-prod
```

Other options per mode (docs pages, append `.md`):

| Mode | Page | Notable options |
| --- | --- | --- |
| HTTP/WEB | `management/core/service/http` | basic/bearer/custom-header/OAuth2 client credentials/SigV4 auth, header and path manipulation, body limits, JSON schema validation, direct responses, retries, CORS, HTTP/2, gRPC mode |
| HTTP plugins | `management/core/service/http-plugins` | rate limiting, caching, Lua, ExtProc, ... |
| SSH | `management/core/service/ssh` | password/private key, host key, subsystems (SFTP), local port forwarding, session recording |
| eSSH | `management/core/service/embedded-ssh` | `config.ssh.eSSHMode: true`; served by `octelium connect --essh` |
| POSTGRES / MYSQL | `.../postgres`, `.../mysql` | forced user/database, password injection, SSL/TLS modes, query-level policies |
| KUBERNETES | `.../kubernetes` | kubeconfig, client certificate or bearer token |
| TCP / UDP / DNS / SOCKS5 / RDP | `.../tcp`, `.../udp`, `.../dns`, `.../socks5`, `.../rdp` | raw proxying, DNS query policies, SOCKS5 embedded mode, browser RDP |
| MCP | `.../mcp/overview`, `.../mcp/plugins` | endpoint, protocol versions, guardrails, tool-level policies |
| LLM | `.../llm/overview`, `.../llm/plugins` | `protocol` (`OPENAI`, `ANTHROPIC`, `GEMINI`, `BEDROCK`), auth injection, model/tool policies, token rate limits |

Base URL for those pages: `https://octelium.com/docs/octelium/latest/`.

## Dynamic configuration

`config` is the default. `dynamicConfig.configs` holds named alternatives; `dynamicConfig.rules`
choose one per request with Policy-style conditions (first match wins; otherwise `config`):

```yaml
kind: Service
metadata:
  name: my-api
spec:
  mode: HTTP
  config:
    upstream:
      url: https://api-v1.example.com
  dynamicConfig:
    configs:
      - name: v2
        upstream:
          url: https://api-v2.example.com
    rules:
      - condition:
          match: ctx.request.http.path.startsWith("/v2")
        configName: v2
```

Docs: https://octelium.com/docs/octelium/latest/management/core/service/dynamic-config.md

## Exposure levels

| Setting | Who can reach it | Extra requirements |
| --- | --- | --- |
| default | Connected clients with an allowing Policy | none |
| `isTLS: true` | Same, over TLS at `<svc>.<ns>.local.<DOMAIN>` | Namespace certificate (`*.local.<DOMAIN>` covers `default`) |
| `isPublic: true` | Also browsers and OAuth2/bearer workloads over the internet, still with Policies | Public DNS and certificate for `*.<ns>.<DOMAIN>` (covered by `*.<DOMAIN>` for `default`) |
| `isPublic` + `isAnonymous` | Anyone on the internet, no authentication | Same as public |

Moving a Service up this table is a security decision. Only do it when the user asks, and say
what becomes reachable by whom.

## Checklist for a new Service

1. Namespace exists (`octeliumctl get ns`); name is `<svc>` or `<svc>.<ns>`.
2. Upstream reachable from where it is served (Cluster network, or the serving User's host).
3. Secrets referenced by `fromSecret` exist (`octeliumctl get sec <name>`).
4. At least one ALLOW path exists for the intended Users, and nothing broader than asked.
5. Native `validate` clean and `apply --dry-run` shows the intended CREATE when supported;
   use `validate_resources.py` and `plan_apply.py` on older CLIs.
6. After apply: `octeliumctl get svc <name> -o yaml` (status addresses), then a real request
   through `octelium connect` or the public URL.
