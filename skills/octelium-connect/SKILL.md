---
name: octelium-connect
description: >-
  Use the octelium client to reach an existing Octelium Cluster as a User. Covers installing the
  CLIs, logging in (browser/IdP, authentication token, OIDC assertion, access token), `octelium
  connect` (detached, rootless, `-p` publishing Services to localhost, `--serve` to host Services,
  embedded SSH/SOCKS5, QUIC), reaching Services by name or FQDN (HTTP, SSH, PostgreSQL, MySQL,
  Kubernetes via `octelium config`), `octelium ssh`/`cp`, running the client in Docker, Kubernetes
  or CI, and fixing login, tunnel and DNS failures. Use when someone wants to access, connect to
  or serve through Octelium. Not for creating Services, Users or Policies (octelium-management)
  or for installing/operating a Cluster (octelium-quick-install, octelium-kubernetes-install,
  octelium-cluster-ops).
license: Apache-2.0
compatibility: Requires the octelium CLI and outbound HTTPS/UDP to the Cluster. Detached mode on Linux needs sudo and systemd.
metadata:
  author: Octelium Labs, LLC
  version: "0.1.0"
  verified-against: octelium v0.43.0
---

# Octelium: connect and access Services

The `octelium` CLI authenticates a User to a Cluster, opens a WireGuard (or QUIC) tunnel, and
lets the machine reach, publish or serve _Services_. A Cluster is addressed by its domain
(e.g. `example.com`); every command needs `--domain <DOMAIN>` or `OCTELIUM_DOMAIN`.

## Scope

- **Use for:** CLI installation, login/logout, `connect`/`disconnect`, reaching Services,
  publishing (`-p`) and serving (`--serve`, `--serve-all`, `--essh`, `--esocks5`), client
  containers/sidecars/CI, and client-side troubleshooting.
- **Hand off:** a missing Service or a denied request that needs a _Policy_ change →
  **octelium-management**. Cluster unreachable because of DNS records, TLS certificates or
  Cluster health → **octelium-cluster-ops**. No Cluster exists yet → an install skill.

## Ground rules

1. **Don't start a browser login unannounced.** `octelium login` (and any authenticated
   command when no Session exists, outside containers/CI) opens a browser on the machine
   running the CLI and blocks until someone approves the login there. Ask the user to run
   `octelium login` themselves, or, if they are at this
   machine and agree, run it with a timeout and tell them to approve it in the browser. On
   remote or headless hosts it can't complete: use an authentication token, OIDC assertion
   or access token instead (see references/authentication.md).
2. **Guard the first authenticated call with a timeout** when you don't know whether a
   Session exists. Prefer the agent's command timeout; `timeout 30 octelium status` works only
   where GNU `timeout` is available. Reuse authorized access; a diagnostic request doesn't
   authorize reading tokens or starting browser login. If the command waits for a browser,
   stop only that process and hand off to the user.
3. **Proxy mode:** if `OCTELIUM_AUTH_PROXY_SOCKET` is set (for example inside a Cordium
   sandbox), the CLI is already authenticated through a local proxy; `login` is refused by
   design. Don't run `login` or `logout` there.
4. **Treat tokens as secrets.** Pass them through `OCTELIUM_AUTH_TOKEN` or a secret store,
   never echo them into logs, commit them, or paste them back in full. Don't log out or
   delete a Session unless asked; that ends the user's access.
5. **Keep exposure minimal.** Publish to loopback (the default) unless the user asks for
   another bind address. Enable `--essh`, `--esocks5`, `--serve` or `--serve-all` only when
   the user asks: they let other authorized Users into this host or its network.
6. **`OCTELIUM_INSECURE_TLS=true` is a temporary workaround**, only for a Cluster whose real
   certificate isn't set yet. Don't persist it in shell profiles, CI or container specs.
7. **Don't invent** Service names, ports, Namespaces, domains or Session names. List them
   (`octelium get svc`, `octeliumctl get sess`) or ask.

## Workflow

1. **Establish context.** Domain; OS; privileges (root/sudo or none); interactive desktop,
   headless server, container, or CI; whether proxy mode is active.
2. **Check the CLI.** `octelium version` (add `--check` to compare with the latest release).
   Install if missing:
   - Linux/macOS: `curl -fsSL https://octelium.com/install.sh | bash`
     (`VERSION=vX.Y.Z`, `INSTALL_DIR=...`, `USE_SUDO=false` are supported env vars)
   - Windows PowerShell: `iwr https://octelium.com/install.ps1 -useb | iex`
   - Homebrew: `brew install octelium/tap/octelium`; Chocolatey: `choco install octelium`
   - Container: `ghcr.io/octelium/octelium`
   The installers ship all three CLIs: `octelium`, `octeliumctl`, `octops`.
3. **Reuse valid access, or authenticate when needed** with the right method → references/authentication.md.
4. **Choose how to connect** (details in references/connecting.md):

   | Situation | Command |
   | --- | --- |
   | Workstation, full access by hostname | `octelium connect -d` (detached; Linux uses `sudo systemd-run`) or foreground `sudo -E octelium connect` |
   | No root, or only a few Services needed | `octelium connect -p <svc>:<port> [-p <svc>.<ns>:<port>]` then use `localhost:<port>` |
   | Container, no capabilities | `connect -p <svc>:<port>` with `OCTELIUM_AUTH_TOKEN` (gVisor userspace mode) |
   | This host must serve a Service | `octelium connect --serve <svc>[.<ns>]` or `--serve-all` |
   | Allow SSH into this host through the Cluster | `octelium connect --essh` |

   Foreground `connect` blocks. Check which timeout/background facilities and privileges are
   available. Retain the handle/PID and private log path for any process you start; see
   references/agent-execution.md. Detached mode may prompt for privileges.
5. **Reach the Service** → references/accessing-services.md. Default Namespace:
   `<svc>` / `<svc>.local.<DOMAIN>`; other Namespaces: `<svc>.<ns>.local.<DOMAIN>`.
6. **Verify** with a real request (`curl`, `ssh`, `psql`), then report what is connected and
   how to stop it. Stop a temporary test tunnel through its retained process handle; leave a
   requested persistent connection running. Don't disconnect unrelated existing connections.

## Diagnose in layers

Identify which layer fails before changing anything; details in references/troubleshooting.md.

1. **Reachability/TLS/DNS of the Cluster** (`login` fails: `produced zero addresses`,
   `x509: certificate signed by unknown authority`, `connection refused`) → Cluster-side
   DNS records, certificate or ingress; hand off to octelium-cluster-ops with the exact error.
2. **Authentication** (no Session, expired, rejected, `PENDING`) → re-authenticate, or an
   admin must approve/fix the Session or User.
3. **Tunnel** (`connect` exits or no interface) → privileges, implementation, UDP egress,
   `OCTELIUM_DEV=true` debug logs.
4. **Name resolution** (tunnel up, `Could not resolve host`) → client DNS; test with
   `-p <svc>:<port>` to bypass DNS.
5. **Authorization/upstream** (resolves, but 403, reset or timeout) → the Service's
   Policies or upstream. Report it; don't try to route around it.

## References

Read only the file the task needs:

| Need | File |
| --- | --- |
| Login methods, workload auth, scopes, devices, authenticators, logout | [references/authentication.md](references/authentication.md) |
| `connect` modes, DNS options, implementations, IP/tunnel modes, serve, eSSH/eSOCKS5, env vars | [references/connecting.md](references/connecting.md) |
| Addressing Services, per-protocol clients, `octelium config`, `ssh`, `cp`, clientless/OAuth2 | [references/accessing-services.md](references/accessing-services.md) |
| Docker, Kubernetes sidecars, Helm, GitHub Actions, headless servers | [references/automation.md](references/automation.md) |
| Error messages and fixes | [references/troubleshooting.md](references/troubleshooting.md) |
| Agent timeouts, background process ownership, cleanup, Claude Code terminal adapter | [references/agent-execution.md](references/agent-execution.md) |
| Exact `octelium` flags (snapshot) | [references/cli-octelium.md](references/cli-octelium.md) |

## Sources of truth

1. `octelium <command> --help` on the installed version: exact flags. Prefer it over the
   bundled snapshot when they differ.
2. Current docs index: https://octelium.com/docs/octelium/latest/llms.txt; every page has a
   Markdown twin at `<page-url>.md` (e.g.
   https://octelium.com/docs/octelium/latest/user/cli/connect.md). Consult them when behavior
   may have changed or the bundled references don't cover the question.
3. The bundled references in this skill.
