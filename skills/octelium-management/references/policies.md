# Policies and access control

Docs: https://octelium.com/docs/octelium/latest/management/core/policy.md
CEL guide: https://octelium.com/docs/octelium/latest/management/guide/cel.md
Schema: https://octelium.com/schemas/octelium/latest/core.v1.Policy.schema.json

## Evaluation

For each request, the policy decision point collects the rules of every Policy that applies:

- attached to or inlined in the **Service** and its **Namespace** (resource side);
- attached to or inlined in the **User**, each of the User's **Groups**, the **Session** (from the
  Credential that created it) and the **Device** if any (principal side);
- **global** Policies in `ClusterConfig.spec.authorization`.

Rules are evaluated by priority: `-4` is highest, `4` lowest, default `0`.

1. Find the highest priority with a matching rule.
2. At that priority, a matching `DENY` wins; otherwise a matching `ALLOW` allows.
3. If no rule matches, deny (default deny).

Rules at lower priorities do not change that decision. Array order does not make an ALLOW
beat a DENY at the same priority.
There is no superuser: even the API server (`default.octelium-api`) is an ordinary gRPC Service
that needs an ALLOW. Session scopes can only narrow the result further.

A standalone Policy has no effect until it is attached (`authorization.policies: [...]`) to a
Service, Namespace, User, Group, Credential (`--policy`), or ClusterConfig. Inline Policies
(`authorization.inlinePolicies: [{spec: {...}}]`) live inside those resources.

Attachment controls scope: `allow-all` on a Service grants access to that Service; on a
Namespace, to its Services. On a User, Group or Session it can grant that principal access to
every Service, including the API; globally it can grant everyone access. Higher-priority rules,
DENY ties and Session scopes still apply. Credential Policies add to User/Group grants; a
narrow Credential ALLOW does not remove broader inherited ALLOWs.

## Rule structure

```yaml
kind: Policy
metadata:
  name: example
spec:
  attrs:                      # optional data for the rules, referenced as attrs.<key>
    allowedGroups: ["dev", "ops"]
  enforcementRules:           # optional preconditions: IGNORE or ENFORCE the whole Policy
    - effect: IGNORE
      condition:
        not: ctx.namespace.metadata.name == "production"
  rules:
    - name: allow-team        # optional
      effect: ALLOW           # ALLOW | DENY
      priority: 0             # -4..4, default 0
      condition:
        match: ctx.user.spec.groups.hasAny(attrs.allowedGroups)
  isDisabled: false           # true stops the Policy from being evaluated
```

Condition types (exactly one per condition):

| Type | Meaning |
| --- | --- |
| `match: <CEL>` | CEL boolean expression |
| `not: <CEL>` | negated CEL expression |
| `matchAny: true` | always matches |
| `all: {of: [conditions]}` | AND |
| `any: {of: [conditions]}` | OR |
| `none: {of: [conditions]}` | NOR |
| `opa: {inline: <rego>}` | OPA Rego, `package octelium.condition`, result in `match`; data under `input.ctx`, `input.attrs` |

`all`/`any`/`none` nest arbitrarily. Quote CEL strings that start with a quote or contain `: `
in YAML, e.g. `match: '"ops" in ctx.user.spec.groups'`.

Enforcement rules: if none match or the list is empty the Policy is enforced; matching `ENFORCE`
rules beat matching `IGNORE` rules.

## The `ctx` request context

| Path | Content |
| --- | --- |
| `ctx.user` | User resource: `metadata.name`, `spec.type` (`HUMAN`/`WORKLOAD`), `spec.email`, `spec.groups`, `spec.attrs` |
| `ctx.groups` | list of the User's Group resources (e.g. `ctx.groups.exists(g, g.spec.attrs.isAdmin)`) |
| `ctx.session` | Session: `metadata.name`, `status.type` (`CLIENT`/`CLIENTLESS`), `status.isBrowser`, `status.authentication.info.type` (`IDENTITY_PROVIDER`, ...), `.info.identityProvider.type` (`OIDC`, `SAML`, ...), `.info.aal` (`AAL1`-`AAL3`), `.info.geoip.country.code`, ... |
| `ctx.device` | Device, when registered: e.g. `status.osType` (`WINDOWS`, ...) |
| `ctx.service` | Service: `metadata.name` (`svc.ns` form), `spec.mode`, `spec.attrs`, `status.namespaceRef.name` |
| `ctx.namespace` | Namespace: `metadata.name`, `spec.attrs` |
| `ctx.request.http` | `method`, `path`, `uri`, `host`, `scheme`, `headers["x"]`, `queryParams.x`, `body` (bytes: `string(...)`), `bodyMap` (parsed JSON) |
| `ctx.request.grpc` | `service`, `serviceFullName`, `package`, `method`, `http.*` |
| `ctx.request.kubernetes` | `verb`, `apiGroup`, `apiVersion`, `namespace`, `resource`, `subresource`, `name`, `http.*` |
| `ctx.request.ssh.connect` | `user` |
| `ctx.request.postgres` | `connect.user`, `connect.database`, `connect.applicationName`, `query.query`, `parse.query` |
| `ctx.request.mysql` | `query.query`, `prepareStatement.query`, `initDB.database` |
| `ctx.request.dns` | `name`, `typeID` |
| `ctx.request.mcp` | `method`, `name` (tool/prompt/resource), `client.name`, `http.bodyMap...` |
| `ctx.request.llm` | `model`, `operation`, `route`, `stream`, `hasTools`, `toolNames`, `hasImageInput`, ... |

Only the sub-object for the Service's mode is populated. Check the mode's doc page ("Access
Control" section) and the Policy/Service schemas before relying on a field; this table is a
summary, not a contract.

## Recipes

Grant a Group access to one Service (resource-based, on the Service):

```yaml
kind: Service
metadata:
  name: grafana
spec:
  mode: WEB
  config:
    upstream:
      url: http://grafana.monitoring.svc:3000
  authorization:
    inlinePolicies:
      - spec:
          rules:
            - effect: ALLOW
              condition:
                match: '"ops" in ctx.user.spec.groups'
```

Grant a Group everything in one Namespace (principal-based, on the Group):

```yaml
kind: Group
metadata:
  name: ops
spec:
  authorization:
    inlinePolicies:
      - spec:
          rules:
            - effect: ALLOW
              condition:
                match: ctx.namespace.metadata.name == "production"
```

Cluster administrators without blanket access to every Service: attach the built-in
`octelium-api-full-access` (management API only) or `octelium-api-read-only` (auditors) instead
of `allow-all`:

```yaml
kind: Group
metadata:
  name: cluster-admins
spec:
  authorization:
    policies: ["octelium-api-full-access"]
```

Read-only HTTP for a Group, everyone else unaffected (reusable Policy attached to a Service):

```yaml
kind: Policy
metadata:
  name: contractors-read-only
spec:
  enforcementRules:
    - effect: IGNORE
      condition:
        not: '"contractors" in ctx.user.spec.groups'
  rules:
    - effect: ALLOW
      priority: -1
      condition:
        match: ctx.request.http.method in ["GET", "HEAD", "OPTIONS"]
    - effect: DENY
      priority: 0
      condition:
        matchAny: true
```

The ALLOW at `-1` wins for read methods; the fallback DENY at `0` denies other methods.
This follows the built-in `http-read-only` and `octelium-api-read-only` Policies. An ALLOW at
the default `0` would tie the DENY and deny read methods too. Attach this to an HTTP/WEB
Service; it ignores non-contractors, whose access is decided by their other Policies.
Other matching rules at a higher priority still win.

Require Sessions labelled AAL3 for humans in production (global, in ClusterConfig; remember
apply replaces the whole ClusterConfig spec):

```yaml
kind: ClusterConfig
metadata:
  name: default
spec:
  authorization:
    inlinePolicies:
      - spec:
          rules:
            - effect: DENY
              condition:
                all:
                  of:
                    - match: ctx.namespace.metadata.name == "production"
                    - match: ctx.user.spec.type == "HUMAN"
                    - not: ctx.session.status.authentication.info.aal == "AAL3"
```

Verify the actual Session authentication info. For IdentityProvider logins, check `aalRules`
and how they map trusted claims (identity-providers docs); without an AAL3 assignment this
denies all humans in production. An administrator-assigned label alone does
not independently verify phishing resistance or compliance with an external assurance standard.

L7 examples (put them in `all.of` with the identity condition):

```yaml
- match: ctx.request.http.path.startsWith("/api/") && ctx.request.http.method == "GET"
- match: ctx.request.kubernetes.verb in ["get", "list", "watch"] && ctx.request.kubernetes.namespace == "staging"
- match: ctx.request.postgres.connect.database == "analytics"
- match: ctx.request.ssh.connect.user != "root"
- match: ctx.request.grpc.serviceFullName == "payments.v1.PaymentService" && ctx.request.grpc.method == "GetInvoice"
```

PostgreSQL checks connection authorization by default. Before using
`ctx.request.postgres.query.query` or `.parse.query` to enforce statement rules, set this in
the Service's active config (and each dynamic config that needs it):

```yaml
config:
  postgres:
    authorization:
      mode: ALL
```

Test both simple-query and extended-query/parse requests. A connection rule alone does not
check every statement. Use database permissions for read-only database access as well.

## Changing Policies safely

1. List every place the change applies: `octeliumctl get pol <name> -o yaml`, then find what
   references it (grep exported Users, Groups, Services, Namespaces, ClusterConfig for the name).
2. Prefer adding a narrow rule on the resource that needs it over editing a shared Policy.
3. Prefer `ALLOW` rules scoped by identity and resource. Set priorities deliberately when
   precedence is needed (such as the read-only recipe above); explain which rules they override.
4. Global (ClusterConfig) and Namespace-level Policies affect many requests: preview with
   native dry-run when supported, or `plan_apply.py`, and state the blast radius.
5. Deleting a Policy that is still attached leaves a dangling reference; detach first.
6. `isDisabled: true` is a reversible way to switch a Policy off for diagnosis; it can open or
   close access, so treat it like any other change.

## Diagnosing "access denied"

1. Pin down the facts: User, Session name (`octeliumctl get sess --user <u>`), Service full name,
   mode, and the request (path/method/query/SSH user/...).
2. Check the prerequisites: User not `isDisabled`; Session `ACTIVE` and not expired
   (`get sess <name> -o yaml`); Device approved if Policies need one; Session scopes (in the
   Session status) include the Service.
3. Collect all applicable Policies: `get svc`, `get ns`, `get user`, each `get grp`, the
   Session's Credential (`get cred`), `get cc` (global), and each attached `get pol`.
4. Evaluate the rules by hand in priority order: which DENY could match, which ALLOW should
   match and why it doesn't (wrong Group name, Service name missing `.namespace`, field path
   typo, wrong mode's `ctx.request.*`).
5. If an OpenTelemetry collector is deployed (`octelium-collector.octelium.svc:8080`, see
   troubleshooting.md), AccessLog entries state `status: ALLOWED|DENIED` and
   `reason.details.policyMatch` naming the Policy or inline Policy that decided.
6. Propose the minimal fix to the user, with the effect stated as "User/Group X gains Y on
   Service Z". Do not apply broader access as a shortcut.
