# Identity: Users, Groups, IdentityProviders, Credentials, Sessions

Docs (append `.md`): `management/core/user`, `group`, `identity-providers`, `credential`,
`session`, `device`, `authenticator`, `user-auth` under
`https://octelium.com/docs/octelium/latest/`.

## Users and Groups

```yaml
kind: User
metadata:
  name: alice
spec:
  type: HUMAN                     # HUMAN (people) | WORKLOAD (machines, CI, services)
  email: alice@example.com        # default identifier for web IdentityProviders
  groups: ["ops"]
  authorization:
    policies: []                  # attach deliberately; see policies.md
---
kind: Group
metadata:
  name: ops
spec: {}
```

- A human logs in through a web IdentityProvider; the Cluster matches the IdP's identifier to
  `spec.authentication.identities[]` (`identityProvider` + `identifier`) first, then to
  `spec.email`. GitHub identifiers are usernames.
- `spec.isDisabled: true` revokes access immediately (reversible).
- `spec.session` overrides ClusterConfig Session durations and `defaultState` per User.
- Groups carry shared Policies and `attrs`; membership is set on the User (`spec.groups`).

## IdentityProviders

The IdP application's redirect/callback URL is `https://<DOMAIN>/callback`. Store the client
secret as a Secret first (`octeliumctl create secret <name>`, value typed by the user).

```yaml
kind: IdentityProvider
metadata:
  name: github
spec:
  displayName: Login with GitHub
  github:
    clientID: <CLIENT_ID>
    clientSecret:
      fromSecret: github-client-secret
---
kind: IdentityProvider
metadata:
  name: okta
spec:
  displayName: Login with Okta
  oidc:
    issuerURL: https://example.okta.com
    clientID: <CLIENT_ID>
    clientSecret:
      fromSecret: okta-client-secret
    checkEmailVerified: true
---
kind: IdentityProvider
metadata:
  name: entra-saml
spec:
  saml:
    metadataURL: https://login.microsoftonline.com/<TENANT>/federationmetadata/2007-06/federationmetadata.xml
```

Workload assertions (no stored secret), used by `octelium login --assertion ...`:

```yaml
kind: IdentityProvider
metadata:
  name: github-actions
spec:
  oidcIdentityToken:
    issuerURL: https://token.actions.githubusercontent.com
    audience: https://example.com
---
kind: User
metadata:
  name: ci-deployer
spec:
  type: WORKLOAD
  authentication:
    identities:
      - identityProvider: github-actions
        identifier: repo:acme/app:ref:refs/heads/main
```

Other `oidcIdentityToken` forms: `jwksURL` + `issuer`, or inline `jwksContent` + `issuer` (for
issuers that don't publish discovery, e.g. private Kubernetes clusters; Kubernetes identifiers
are `system:serviceaccount:<ns>:<sa>`). Options such as `identifierClaim`, `scopes`,
`useUserInfoEndpoint`, `disableEmailAsIdentity`, SAML `identifierAttribute`/`forceAuthn`, and
`aalRules` (to assign `AAL1`-`AAL3` from assertion claims) are in the IdentityProvider schema
and docs. Don't guess an IdP's issuer URL or claim names; ask or check the provider's docs.

## Credentials

```bash
octeliumctl create cred --user ci-deployer                          # auth token (default type)
octeliumctl create cred --user ci-deployer --expire-in 30days --policy deploy-only ci-token
octeliumctl create cred --user bootstrap --one-time --expire-in 1hour   # single use
octeliumctl create cred --user svc-a --max-authn 10
octeliumctl create cred --user svc-a --type oauth2                  # prints Client ID + Client Secret
octeliumctl create cred --user svc-a --type access-token             # static bearer token (creates a Session now)
octeliumctl create cred --user svc-a --session-type clientless       # token for SDK/clientless use
octeliumctl create cred --rotate ci-token                            # new token; old one stops working
octeliumctl update cred ci-token --disable | --enable | --expire-in 7days | --policy p1 --policy p2
octeliumctl get cred --user ci-deployer
octeliumctl delete cred ci-token
```

- The token/secret is printed once. Deliver it to the user; don't store it in files, logs or
  chat history. `-o json` output also contains it.
- `--policy` Policies are copied into every Session the Credential creates, on top of the
  User's and Groups' Policies. Use them to narrow what a token is for (they can also grant, so
  keep them minimal).
- Prefer short `--expire-in`, `--one-time` for bootstrap, and OIDC assertions over long-lived
  tokens for CI and Kubernetes.
- `--expire-in` accepts values like `600seconds`, `45minutes`, `7hours`, `3days`, `2weeks`,
  `6months`.

## Sessions, Devices, Authenticators

```bash
octeliumctl get sess [--user alice] [-o yaml]
octeliumctl update session <name> --approve | --reject | --expire-in 2hours
octeliumctl delete session <name>                 # logs that client out immediately
octeliumctl get dev [--user alice];  octeliumctl update device <name> --approve | --reject
octeliumctl get authn [--user alice]; octeliumctl update authenticator <name> --approve | --reject
```

Session types: `CLIENT` (octelium/octeliumctl) and `CLIENTLESS` (browser, OAuth2, access tokens,
SDK). States: `ACTIVE`, `PENDING` (awaiting approval), `REJECTED`. Default states and durations
come from ClusterConfig `spec.session.human|workload` and per-User `spec.session`.

## First admin and retiring the initial token

A new Cluster has a `root` WORKLOAD User and a `root-init` authentication token whose Sessions
carry an inline allow-all Policy. `root` itself has no Policies. Replace it with named admins:

1. Create the admin identity and access path in one apply: a Group with the management Policy
   (`octelium-api-full-access`, or `allow-all` only if the user wants unrestricted access), the
   admin User(s) in that Group, and an IdentityProvider they can log in with (plus its Secret,
   created first).
2. Validate, plan, apply.
3. The admin logs in from their own machine (`octelium login --domain <DOMAIN>`) and confirms
   `octeliumctl get ns` works.
4. Only then, and only if the user wants it: `octeliumctl delete cred root-init` (and optionally
   the `root` User). A new Credential created for `root` without `--policy` would have no access,
   because the allow-all lives in the `root-init` Credential, not in the User.

Template: `assets/templates/first-admin.yaml`.

If every admin is locked out, API access can only be restored from the Kubernetes side (see the
octelium-cluster-ops skill, "access recovery").
