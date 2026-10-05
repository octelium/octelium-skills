# Resource model

Docs: https://octelium.com/docs/octelium/latest/reference/resources.md

Every resource has `apiVersion: core/v1`, `kind`, `metadata` (`name`, optional `displayName`,
`description`, `labels`, `annotations`, `tags`, `picURL`; the rest is server-managed), `spec`,
and server-managed `status`. Secret and Config also carry `data`.

## Kinds

| Kind | Purpose | Managed by | Schema |
| --- | --- | --- | --- |
| Service | A protected resource behind an identity-aware proxy (Vigil) | apply | `core.v1.Service` |
| Namespace | Groups Services; part of their DNS names | apply / `create ns` | `core.v1.Namespace` |
| Policy | Reusable access-control rules | apply | `core.v1.Policy` |
| User | `HUMAN` or `WORKLOAD` identity | apply | `core.v1.User` |
| Group | Set of Users for shared Policies | apply | `core.v1.Group` |
| IdentityProvider | `github`, `oidc`, `saml`, `oidcIdentityToken` authentication | apply | `core.v1.IdentityProvider` |
| Credential | Authentication token, OAuth2 client credentials, or access token for a User | `create cred` (apply possible) | `core.v1.Credential` |
| Secret | Sensitive value referenced by name (`fromSecret`) | `create secret` (apply with `--include-secret`) | `core.v1.Secret` |
| Config | Non-sensitive data (`value`, `valueBytes`, `dataMap`, `attrs`) | `create config` / apply | `core.v1.Config` |
| ClusterConfig | Cluster-wide settings (single resource) | apply (whole spec) | `core.v1.ClusterConfig` |
| Session | An authenticated login; `CLIENT` or `CLIENTLESS` | read, `update session`, delete | `core.v1.Session` |
| Device | A registered User machine | read, approve/reject, delete | `core.v1.Device` |
| Authenticator | FIDO/TOTP/TPM factor of a User | read, approve/reject, delete | `core.v1.Authenticator` |
| Gateway | One per data-plane node; tunnel endpoint | read only | `core.v1.Gateway` |
| Region | A Kubernetes cluster backing the Cluster (`default`) | read only | `core.v1.Region` |
| AccessLog, ComponentLog | Log record formats (OpenTelemetry) | not stored as resources | `core.v1.AccessLog`, `core.v1.ComponentLog` |
| PolicyTrigger | Policy-related trigger resource | not managed by apply | `core.v1.PolicyTrigger` |

Schema URL pattern:
`https://octelium.com/schemas/octelium/latest/core.v1.<Kind>.schema.json`
(bundled snapshot: `assets/schemas/core.v1.<Kind>.schema.json`; draft-04, with
`additionalProperties: false`). The Service schema is large (~200 KB): don't read it whole;
query it, e.g.

```bash
jq '.definitions | keys[]' assets/schemas/core.v1.Service.schema.json | grep -i postgres
jq '.definitions["octelium.api.main.core.v1.Service.Spec"].properties | keys' assets/schemas/core.v1.Service.schema.json
jq '.definitions["octelium.api.main.core.v1.Service.Spec"].properties.mode.enum' assets/schemas/core.v1.Service.schema.json
```

## Naming

- A name segment must match `^[a-z][a-z0-9-]{0,38}[a-z0-9]$`: 2 to 40 characters, starts with a
  lowercase letter, no leading/trailing or consecutive hyphens. Only Services take a second
  `.namespace` segment.
- **Service names include the Namespace:** `metadata.name: web` means `web.default`;
  `web.production` places it in the `production` Namespace (which must exist first). Use the same
  form with `get`, `delete`, `-p`, `--serve` and in Policy conditions
  (`ctx.service.metadata.name == "web.production"`).
- A Service named `default` in a Namespace (`default.production`) additionally answers at
  `production.local.<DOMAIN>`.
- DNS: private `<svc>.<ns>.local.<DOMAIN>` (default Namespace also `<svc>.local.<DOMAIN>`);
  public (when `isPublic`) `<svc>.<ns>.<DOMAIN>` (default Namespace also `<svc>.<DOMAIN>`).

## Built-in resources

Created during installation and **not** marked system, so you can edit or delete them, and
`apply --prune` deletes them if they are missing from your files:

| Kind | Name | What it is |
| --- | --- | --- |
| User | `root` | `WORKLOAD` User owning the initial token. Has no Policies of its own. |
| Credential | `root-init` | Initial authentication token for `root`, valid ~6 months, with an inline allow-all Policy passed to its Sessions. Delete it once you have your own admins. |
| Policy | `allow-all` | Single rule `ALLOW` `matchAny: true`. |
| Policy | `deny-all` | Single rule `DENY` `matchAny: true`. |
| Policy | `octelium-api-full-access` | `ALLOW` (priority -1) any gRPC method on Services in the `octelium-api` Namespace. |
| Policy | `octelium-api-read-only` | Only `Get*`/`List*` methods of the Octelium APIs (not the auth/user APIs). |
| Policy | `http-read-only` | Read-only HTTP methods. |
| Service | `demo-nginx` (default) | Public `WEB` demo managed container. |
| Service | `essh.octelium` | Embedded SSH Service used by `octelium ssh`/`cp`. |
| Service | `socks5.octelium` | Embedded SOCKS5 Service. |

System resources (excluded from apply's current-state comparison and prune): Namespaces `default`, `octelium`, `octelium-api`;
Services such as `default.octelium-api` (the API server, a gRPC Service), `auth.octelium-api`,
`dns.octelium`, `portal.default`, `default.default`; the system `octelium` User; hidden internal
Secrets. Access to the management API is itself governed by Policies on the `octelium-api`
Namespace's Services.

Filter system resources out of desired exports. Including them as desired documents can make
apply attempt creates that the server rejects; the system flag in a file is not a skip rule.

Packages (Cordium, Enterprise) may add their own resources. Inspect with `get` before pruning.

## `attrs`

User, Group, Service and Namespace accept `spec.attrs` (arbitrary structured data, camelCase keys
recommended) usable in Policies as `ctx.user.spec.attrs.x`, `ctx.service.spec.attrs.x`, etc.
Policies have their own `spec.attrs` referenced as `attrs.x`.
