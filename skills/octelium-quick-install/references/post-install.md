# After the installer: DNS, TLS, first login

Docs: https://octelium.com/docs/octelium/latest/overview/quick-install.md (Post-Installation)

## 1. Public DNS

In the DNS provider for `<DOMAIN>` (the user does this, or you do it with their DNS API tooling
and consent):

| Type | Name | Value |
| --- | --- | --- |
| `A` | `<DOMAIN>` | public IPv4 of the host (the `public IPv4` line of the installer summary) |
| `CNAME` | `*.<DOMAIN>` | `<DOMAIN>` (a wildcard `A` to the same IP is equivalent) |

Check from outside the host: `dig +short <DOMAIN>` and `dig +short octelium-api.<DOMAIN>` must
both return the IP. With `--quicv0`, also create an `A`/`AAAA` record for each Gateway hostname
(`octeliumctl get gw -o yaml` → `status.hostname`, `status.publicIPs`).

If the domain is proxied by a CDN (e.g. Cloudflare orange cloud), use DNS-only mode: the Ingress
terminates TLS itself and WireGuard traffic isn't HTTP.

## 2. TLS certificate

The Cluster starts with a self-signed certificate. It needs a publicly trusted certificate whose
SANs include:

- `<DOMAIN>`
- `*.<DOMAIN>`
- `*.local.<DOMAIN>` (recommended: TLS for private Services in the `default` Namespace)

Wildcards require the ACME DNS-01 challenge.

Manual, one-off (certbot prompts for TXT records; the user must create them, so hand this to the user):

```bash
certbot certonly --manual --preferred-challenges dns --agree-tos --email <EMAIL> \
  --cert-name <DOMAIN> -d "<DOMAIN>,*.<DOMAIN>,*.local.<DOMAIN>"
```

Automated renewal is preferable (Let's Encrypt certificates last 90 days):

- a certbot DNS plugin for the user's provider (e.g. `certbot-dns-cloudflare`) plus a deploy hook
  that re-runs `octops cert`, or
- cert-manager inside the K3s cluster writing the Secret `cert-cluster` in namespace `octelium`
  (example in the octelium-cluster-ops skill).

Install the certificate on the host:

```bash
octops cert <DOMAIN> \
  --cert /etc/letsencrypt/live/<DOMAIN>/fullchain.pem \
  --key /etc/letsencrypt/live/<DOMAIN>/privkey.pem \
  --kubeconfig /etc/rancher/k3s/k3s.yaml
```

`octops cert` updates the Kubernetes TLS Secret `cert-cluster` in namespace `octelium`, which the
Cluster watches. Without a TTY it doesn't prompt; run it within the user's authorized
installation or certificate-rotation plan. Ask only if the target or change is unresolved. Verify:
`curl -sI https://<DOMAIN>` succeeds without `-k`.

## 3. First login and admin

The installer summary shows the initial token path. With `OCTELIUM_SKIP_MESSAGES=true`, init
suppresses the token-bearing login message. Historical unsuppressed runs can contain that
message in the terminal and install log; don't read raw logs into the transcript.

- The user runs the login on their own machine (install the CLI there first:
  `curl -fsSL https://octelium.com/install.sh | bash`). Transfer the token privately into a
  mode-0600 file on that machine. The user runs
  `OCTELIUM_AUTH_TOKEN="$(cat /private/path/init-token)" octelium login --domain <DOMAIN>`,
  then removes the local copy. Don't paste it into chat, tickets, or command-line arguments.
- Before step 2 is done, login fails with `x509: certificate signed by unknown authority`;
  prefix that one command with `OCTELIUM_INSECURE_TLS=true` if the user wants to continue now.
- This token belongs to the `root` User through the `root-init` Credential (valid about six
  months, full access). Next: create named admins with an IdentityProvider, verify their login,
  then delete `root-init` (octelium-management skill, "First admin").
- Quick check: `octelium connect -p demo-nginx:9000` then `curl localhost:9000`
  (the built-in demo Service).

## 4. Hardening a single-node Cluster

- Keep the host patched and SSH key-only. K3s's API listens on TCP `6443`; the installer doesn't
  open it in ufw/firewalld, but if the host has no firewall, block it in the cloud firewall except
  from trusted addresses.
- Back up `/etc/octelium/installer` and the database together (the password and the data belong
  together), plus installation/Bootstrap settings, certificates/private keys and encryption key
  material where applicable. A logical dump is portable; capture it to a private new file as
  below and store it encrypted. Test the restore for the intended recovery objective. A resource
  API export is configuration migration, not a complete backup.
- For access logs, deploy an OpenTelemetry collector as `octelium-collector` in namespace
  `octelium` (octelium-management troubleshooting reference).
- Plan upgrades with `octops upgrade <DOMAIN> --check` (octelium-cluster-ops).

From Bash in an authorized backup directory:

```bash
(
  set -euo pipefail
  umask 077
  dump_file="$(mktemp ./octelium-backup.XXXXXX.sql)"
  if kubectl -n default exec statefulset/octelium-postgresql -c postgres -- sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump --host=127.0.0.1 --username="$POSTGRES_USER" octelium' > "$dump_file"; then
    printf '%s\n' "$dump_file"
  else
    rm -f "$dump_file"
    exit 1
  fi
)
```

Dumps contain Octelium Secret values in plaintext. Keep the directory private, encrypt the
backup, and never print its contents into the transcript. A failed dump is removed rather than
reported as a backup.
