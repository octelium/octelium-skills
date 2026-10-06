# Access control

Docs: https://octelium.com/docs/cordium/latest/how.md,
https://octelium.com/docs/octelium/latest/management/core/policy.md

Three layers decide what happens:

1. **Octelium Policies** decide whether a User may call the Cordium API and open the console.
2. **The Cordium API** then checks ownership and the caller's role in the Space.
3. **Octelium Policies** decide which Services each Workspace Session may reach.

## Authentication

`cordium` has no `login` command: it uses the Session saved by `octelium login` (same
`OCTELIUM_HOME`, `--domain`/`OCTELIUM_DOMAIN`, `--homedir`, `--logout`). The User runs
`octelium login --domain <DOMAIN>` (browser) on a workstation; CI and headless hosts use an
authentication token or OIDC assertion of a `WORKLOAD` User (octelium-connect covers the
methods). An authenticated command without a Session starts a browser login, so check with
`octelium status` under a timeout first.

## Cordium API and Services

| Target | Default access | Used by |
| --- | --- | --- |
| gRPC `octelium.api.main.cordium.v1.MainService` on Service `default-cordium.octelium-api` | Allowed for every authenticated User by the Service's built-in inline Policy | Creating, reading, starting, stopping and deleting resources |
| gRPC `octelium.api.main.cordium.v1.WorkspaceService` (same Service) | Needs an ALLOW | `cordium exec`, `terminal`, `logs`, the terminal of `cordium run` |
| gRPC `octelium.api.main.cordium.v1.ManagementService` (same Service) | Needs an ALLOW | `cordium man get cc`, `cordium man apply` |
| Service `default.cordium` | Needs an ALLOW | Web console `https://cordium.<DOMAIN>` and Workspace applications |
| Service `default-ssh.cordium` | Built-in inline ALLOW for everyone | `cordium ssh`, `cordium cp`, SSH clients; Cordium then requires Workspace ownership |

Admins holding `octelium-api-full-access` (any method in the `octelium-api` Namespace) already
pass the API layer. For other Users, attach a Policy like this to their Group (octelium-management
covers exporting and re-applying the Group with the Policy name in
`spec.authorization.policies`):

```yaml
kind: Policy
metadata:
  name: cordium-users
spec:
  rules:
    - name: cordium-api
      effect: ALLOW
      priority: -1
      condition:
        match: >-
          ctx.namespace.metadata.name == "octelium-api" &&
          ctx.request.grpc.serviceFullName in ["octelium.api.main.cordium.v1.MainService",
          "octelium.api.main.cordium.v1.WorkspaceService"]
    - name: cordium-console
      effect: ALLOW
      condition:
        match: ctx.namespace.metadata.name == "cordium"
```

Grant `octelium.api.main.cordium.v1.ManagementService` only to Cordium administrators: it
reads and replaces the Cluster-wide Cordium settings. A denied API call surfaces as
`PermissionDenied`/`Unauthorized`; don't widen these rules to fix a User's denial without the
user's explicit request.

## Ownership and Space roles

The API enforces these checks after the Policies allow the call:

| Operation | Who |
| --- | --- |
| Get, start, stop, update, delete a Workspace; exec, terminals, logs, SSH | The Workspace owner only |
| Create a Workspace in a Space | Any Member of the Space |
| Read a Space, its Templates, GitProviders, Volumes, Memberships; list Secrets | Any Member |
| Read a single Secret (metadata only) | ADMIN or OWNER |
| Create Templates, Secrets, GitProviders, Volumes; update Templates and Volumes; delete Secrets and Volumes; pre-builds | ADMIN or OWNER |
| Update or delete a GitProvider, delete a Template, update or delete a Space | Its creator (while still a Member) or an OWNER |
| Add, change or remove Members | ADMIN or OWNER; granting or removing OWNER needs an OWNER |
| WorkspaceSnapshots | Their owner; restoring requires Membership in the snapshot's Space |
| Create a Space | Users matched by ClusterConfig `spec.space.ownership` (references/cluster-config.md) |

Roles are `OWNER`, `ADMIN` and `USER` (the default). Members can only be added to ORGANIZATION
Spaces, by email or User reference of an existing User; a new OWNER must also be allowed to own
Spaces by the ClusterConfig. Space creators can't leave or be removed; they delete the Space
instead. The CLI has no Membership commands: manage Members in the web console (or the API).

## Workspace identity

Each Workspace run gets a new Octelium Session (`CLIENT`, authentication type `INTERNAL`, owned
by the Workspace owner, valid up to 90 days) that is deleted when the run stops. Inside the
Workspace, `octelium connect` runs with this Session, so the Workspace reaches exactly the
Services its owner's Policies allow, by name (`<svc>`, `<svc>.<ns>`) or FQDN, with secretless
credential injection at the Octelium proxy. The Session also authenticates the `octelium`,
`octeliumctl` and `cordium` CLIs inside the Workspace through the proxy socket.

The Session carries Cordium details under `status.ext.cordium`: `workspaceRef`, `spaceRef`,
`templateRef` and `spaceType`. Inspect a running Workspace's Session first:
`octeliumctl get sess <session-name> -o yaml` (the name is in `cordium get ws <ws> -o yaml` at
`status.sessionRef`). Use it to give agents less than their owner, for example a DENY attached
to a sensitive Service (octelium-management):

```yaml
kind: Policy
metadata:
  name: deny-cordium-workspaces
spec:
  rules:
    - name: deny-workspace-sessions
      effect: DENY
      priority: -2
      condition:
        match: '"ext" in ctx.session.status && "cordium" in ctx.session.status.ext'
```

Check the result with a real request from a Workspace and from the owner's own client.

Other controls for agents and untrusted code:

- **A dedicated User.** Run agents under a `WORKLOAD` User whose Policies grant only the
  Services the task needs, instead of a human admin's account.
- **Egress rules.** `runtime.network.egress` with `defaultAction: DENY` and narrow ALLOW rules
  limits direct network access (references/workspace-spec.md).
- **Serving.** `runtime.octelium.serveAll`/`serveServices` (`--serve-all`, `--serve`) let the
  Workspace host Services for other Users; enable only on request.
- **SSH.** `spec.authorization.disableSSH: true` on a Space denies SSH to all its Workspaces.
- **Sharing applications.** `ShareWorkspacePort` (web console or API) exposes an application to
  the Space's Members (`MEMBERS`) or every User (`ALL`); without sharing only the owner can open
  it.

## Diagnosing denials

1. Which layer? `PermissionDenied`/`Unauthorized` from the Octelium proxy before the Cordium
   API, a Cordium message such as `The User is not a Member in this Space`, or a refused
   connection from inside the Workspace.
2. Policy layer: compare with the table above and the User's Groups and Policies
   (octelium-management; access logs name the matching Policy).
3. API layer: `cordium get spc <space> -o yaml` and the Members list in the console.
4. Workspace layer: the Service's Policies for the owner User and any Workspace-Session rules.
