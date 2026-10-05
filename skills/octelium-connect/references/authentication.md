# Authentication

A User can only interact with a Cluster through a valid _Session_, created by a successful
authentication. `octelium` and `octeliumctl` share the same local state, so logging in with
either one works for both.

Docs: https://octelium.com/docs/octelium/latest/user/cli/authentication.md

## Choosing a method

| Who / where | Method | Notes |
| --- | --- | --- |
| Human on a machine with a browser | `octelium login` (or `--web`) | Opens `https://<DOMAIN>/login`, waits for approval through a local callback. Must be run by the human. |
| Human on a headless server | Web login cannot complete there. Use an authentication token issued for the User, or connect from a machine with a browser. | Ask an admin for a token if needed. |
| Workload (server, container, VM) | `OCTELIUM_AUTH_TOKEN` | Token is an authentication-token _Credential_ (`octeliumctl create cred --user <user>`). |
| Workload with an OIDC identity (Kubernetes SA, GitHub Actions, Azure, generic JWT) | `--assertion <type>[:options]` or `OCTELIUM_AUTH_ASSERTION` | Secretless; needs an `oidcIdentityToken` _IdentityProvider_ and a matching identity on the User. |
| Short-lived scripts or serverless | `OCTELIUM_ACCESS_TOKEN=<token>` | No login step; the token is used directly. |
| Inside a Cordium sandbox / proxy mode | Nothing to do | `OCTELIUM_AUTH_PROXY_SOCKET` is set; `login` is refused by design. |

## Commands

```bash
export OCTELIUM_DOMAIN=example.com            # PowerShell: $env:OCTELIUM_DOMAIN = "example.com"

octelium login                                # browser/IdP (human runs it)
OCTELIUM_AUTH_TOKEN="$TOKEN" octelium login   # authentication token, kept out of argv
OCTELIUM_AUTH_TOKEN="$TOKEN" octelium connect # authenticate and connect in one step

octelium login --assertion k8s                            # service account token at /var/run/secrets/kubernetes.io/serviceaccount/token
octelium login --assertion github-actions                 # audience defaults to the Cluster domain
octelium login --assertion github-actions:audience=custom-aud
octelium login --assertion azure[:audience=custom-aud]
octelium login --assertion jwt:file=/path/to/jwt
octelium login --assertion jwt:env=JWT_VAR

octelium status                               # who am I, which Session, Cluster info (-o yaml|json)
octelium logout                               # deletes the Session locally and on the Cluster
```

Supply `TOKEN` through a secret store or a private file, not a literal assignment in shell
history. Prefer the environment variable over `--auth-token`: command-line arguments are
visible in the process list and shell history. The agent must not read the token into output.

`--logout` is a global flag that logs out after the command finishes. It is useful in
ephemeral environments (e.g. `octelium connect --logout ...` in a container) so that
Sessions don't accumulate.

## Scopes

Scopes voluntarily narrow a Session's permissions below what Policies grant. They only apply
when authenticating with `--auth-token` or `--assertion`, and they never widen access.

```bash
OCTELIUM_AUTH_TOKEN="$TOKEN" octelium login --scope "service:svc1"     # one Service in the default Namespace
OCTELIUM_AUTH_TOKEN="$TOKEN" octelium login --scope "service:svc1.ns1" # one Service in ns1
OCTELIUM_AUTH_TOKEN="$TOKEN" octelium login --scope "service:ns2/*"    # every Service in ns2
OCTELIUM_AUTH_TOKEN="$TOKEN" octelium login --scope "api:core"         # only the Core API
OCTELIUM_AUTH_TOKEN="$TOKEN" octelium login --scope "api:core.MainService/ListService"
```

Use scopes to give automation least privilege; they are not a replacement for Policies.

Docs: https://octelium.com/docs/octelium/latest/user/scope.md

## Multiple Clusters and profiles

- Each command targets the domain in `--domain` or `OCTELIUM_DOMAIN`. Sessions for several
  Clusters can coexist.
- `OCTELIUM_HOME=<dir>` (or the global `--homedir <dir>` flag) selects a different state
  directory, which works as a separate profile (e.g. two identities for the same Cluster).
  `OCTELIUM_HOME=mem` keeps state in memory only.
- Default state directory: `~/.config/octelium` (Linux), `~/Library/Application Support/octelium`
  (macOS), `%AppData%\Octelium` (Windows). Treat it as sensitive: it holds Session tokens.

## Session lifecycle

- Access tokens are short-lived (4 hours by default) and refreshed automatically while the
  refresh token is valid. When the refresh token expires, the Session is gone and the User
  must authenticate again.
- A Session can be `PENDING` or `REJECTED` if the Cluster requires approval. The User cannot
  fix that; an admin approves it with `octeliumctl update session --approve <name>`.
- Admins can revoke Sessions and disable Users at any time; that takes effect on the next
  request regardless of token validity.

## Devices and Authenticators (MFA)

```bash
octelium auth device                 # register/enroll this Device (alias: auth dev)
octelium auth get authn              # list your Authenticators
octelium auth create authn --type tpm [--display-name "Laptop TPM"]
octelium auth create authn --type totp --display-name "Phone"
octelium auth authn <authenticator-name>   # authenticate the current Session with it
octelium auth delete authn <authenticator-name>
```

FIDO2/passkeys are registered through the web Portal ("Authenticators" in the sidebar), not the
CLI. Whether Devices or Authenticators are required is decided by the Cluster's Policies and
ClusterConfig, not by the client.
