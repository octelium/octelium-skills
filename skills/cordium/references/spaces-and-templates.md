# Spaces, Memberships, Templates and GitProviders

Docs: [Spaces and Members](https://octelium.com/docs/cordium/latest/workspaces/spaces.md),
[Templates and pre-builds](https://octelium.com/docs/cordium/latest/workspaces/templates.md),
[GitProviders](https://octelium.com/docs/cordium/latest/workspaces/secrets.md#gitproviders).
Worked example: [fast startup with pre-builds](https://octelium.com/docs/cordium/latest/examples/workflows/prebuilds.md).

## Spaces

| | USER Space | ORGANIZATION Space |
| --- | --- | --- |
| Full name | `<space>.<owner-user>` | `<space>.cordium` |
| Create | `cordium create space <space>` | `cordium create space <space>.cordium` |
| Members | Owner only | Any number, with Roles |
| `spec.limit` | Not allowed | `defaultLimit`, `maxLimit` |
| Secret-sourced Space env vars | Not allowed | Allowed |

Creating additional Spaces of either kind needs a matching ClusterConfig ownership rule
(installation default: everyone). The automatic personal `default` Space is exempt. Creating a Space
also creates the creator's OWNER Membership and a `default` Template. Each User gets
`default.<user>` automatically on their first Workspace without `--template`/`--space`.

Space spec fields, edited in the web console (or `UpdateSpace` in the API), cascade to every
Workspace of the Space at its next start:

```yaml fragment
spec:
  limit:                      # ORGANIZATION only
    maxLimit:                 # hard cap per Workspace
      cpu: {millicores: 8000}
      memory: {megabytes: 16384}
      storage: {megabytes: 100000}
  runtime:
    envVars:
      - key: COMPANY_REGISTRY
        value: registry.example.com
    tasks:
      - name: banner
        type: POST_START
        run: echo "Workspace of the platform Space"
    capabilities:
      drop: [NET_RAW]
  authorization:
    disableSSH: true          # deny SSH to all Workspaces of the Space
```

Deleting a Space deletes all its Workspaces (and their Sessions), Templates, Secrets, Volumes,
WorkspaceSnapshots, GitProviders and Memberships. Only an OWNER can do it.
Use `cordium delete space <name>` or the portal within the user's authorized scope. Members
other than the creator leave a Space in the portal.

## Memberships

Roles: `OWNER` (everything, including the Space and its OWNERs), `ADMIN` (Templates, Secrets,
GitProviders, Volumes, pre-builds, Members) and `USER` (create and use Workspaces). Members are
added by the email or reference of an existing Octelium User, only to ORGANIZATION Spaces. The
CLI has no Membership commands: use the web console ("Members" of the Space) or the API. Full
permission matrix: references/access-control.md.

## Templates

A Template is a reusable Workspace spec (`image`, `runtime`, `repository`,
`additionalRepositories`, `limit`, `vars`, `gitProvider`). Every Space has `default`, which can't
be deleted. Workspaces read their Template at every start, so runtime changes (env vars,
`POST_START` tasks) reach existing Workspaces on their next start; image and `ON_CREATE` changes
apply to fresh runs only.

```bash
cordium create template node.my-project --image node:22-bookworm \
  --repository https://github.com/myorg/web --cpu 4000 --memory 8192
cordium create template backend.my-project -f backend-template.yaml
cordium create template api.platform.cordium -f api.yaml --git-provider github.platform.cordium
cordium get tmpl --space my-project
cordium get tmpl backend.my-project -o yaml
cordium get ws --template backend.my-project          # who uses it, before changing it
```

Flags combine with `-f` and override it: `--image`/`--dockerfile`, `--repository`, `--branch`,
`--depth`, `--checkout`, `-e`, `--env-from-secret KEY=<full Secret name>`,
`--additional-repo NAME=URL`, `--cpu`, `--memory`, `--storage`, `--git-provider <full name>`.
There is no update command: change a Template in the web console (Template settings) or with
`UpdateTemplate` (whole spec replaced). Deleting a Template needs an ADMIN or OWNER and
has no prompt; check its Workspaces first.

### Pre-builds

A pre-build runs a hidden build Workspace from the Template (ClusterConfig `buildLimit`, default
2000 millicores, 6000 MB, 20000 MB), pulls or builds the image, clones, runs the non-background
`ON_CREATE` and `POST_START` tasks (background and `PRE_STOP` tasks are skipped), then snapshots
its storage. New Workspaces of the Template restore from the latest ready snapshot and skip the
image build and `ON_CREATE` tasks.

```bash
cordium build backend.my-project            # ADMIN or OWNER; starting another cancels a running one
cordium build backend.my-project --cancel
cordium get tmpl backend.my-project -o json | jq '.status.buildInfo'
```

Pre-builds do not run `octelium connect`: they have no secretless access. They also skip
dotfiles, GitProvider credentials, background tasks and `PRE_STOP`. Private git therefore
needs a Space Secret for a pre-build. Restored Workspaces apply their own dotfiles and runtime
configuration and run `POST_START` normally.

Requirements: a CSI driver with VolumeSnapshot support and a VolumeSnapshotClass
(references/storage.md). Rebuild after changing the Template's image, repository or `ON_CREATE`
tasks; until then new Workspaces start from the old snapshot. A failed build is recorded in
`status.buildInfo.builds[].failure` with the same failure types as Workspaces.

## GitProviders

A GitProvider holds an OAuth2 application; a Template that names it gets the starting User's
OAuth2 token injected into its Workspaces (git credential helper, plus git `user.name` and
`user.email`), so private clones and pushes need no Secret in the spec.

1. Register an OAuth app at the provider with the callback
   `https://cordium.<DOMAIN>/auth/v1/callback`.
2. Store its client secret as a Space Secret (the user types it):
   `cordium create secret github-oauth.my-project`.
3. Create the GitProvider (ADMIN or OWNER), with full names:

```bash
cordium create gitprovider github.my-project --type github \
  --client-id <client-id> --client-secret-from-secret github-oauth.my-project.<you>
cordium create gitprovider forgejo.platform.cordium --type oauth2 \
  --client-id <client-id> --client-secret-from-secret forgejo-oauth.platform.cordium \
  --auth-url https://git.example.com/login/oauth/authorize \
  --token-url https://git.example.com/login/oauth/access_token --scope read:user --scope repo
```

4. Attach it: `gitProvider: github.my-project.<you>` in the Template spec, or
   `--git-provider` when creating the Template.
5. Create a stopped Workspace, open its portal page, and sign in to the GitProvider before
   starting. The token is reused on later runs until it expires, when the User signs in again.
   It is available through the git credential helper to processes inside the Workspace.

| Type | Endpoints | Default scopes |
| --- | --- | --- |
| `github` | github.com | `read:user`, `user:email`, `repo` |
| `gitlab` | gitlab.com | `read_user`, `write_repository` |
| `oauth2` | `--auth-url`, `--token-url` (required) | None: at least one `--scope` is required |

Use `oauth2` for self-managed GitLab, Gitea or Forgejo. At most 10 scopes. Qualify the
GitProvider name with its Space.
