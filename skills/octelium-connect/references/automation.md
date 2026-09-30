# Running the client unattended

Workloads authenticate as `WORKLOAD` Users with an authentication token, an OIDC assertion or
an access token (see authentication.md). Prefer assertions (no stored secret) where the platform
issues OIDC tokens: Kubernetes service accounts, GitHub Actions, Azure managed identities.

Creating the WORKLOAD User, its Credential or its assertion IdentityProvider is an admin task
(octelium-management skill).

## Docker / Podman

```bash
# TUN/kernel mode: Services reachable by name inside the container
docker run --cap-add NET_ADMIN -e OCTELIUM_DOMAIN=<DOMAIN> -e OCTELIUM_AUTH_TOKEN \
  ghcr.io/octelium/octelium connect

# Force TUN mode: add the device, or the MKNOD capability
docker run --cap-add NET_ADMIN --device /dev/net/tun ... ghcr.io/octelium/octelium connect ...

# No capabilities at all: gVisor userspace mode, publish what you need
docker run -e OCTELIUM_DOMAIN=<DOMAIN> -e OCTELIUM_AUTH_TOKEN \
  ghcr.io/octelium/octelium connect -p svc1:8080 -p svc2:8081
```

Pass the token through the environment (`-e OCTELIUM_AUTH_TOKEN` copies it from the caller's
environment) or a secret mechanism, not as `--auth-token` on the command line. Rootless
containers with user-namespaced `NET_ADMIN` work as well. Inside containers the local DNS
server is used by default.

## Kubernetes sidecar or connector Deployment

```yaml
containers:
  - name: octelium
    image: ghcr.io/octelium/octelium
    command: ["octelium"]
    args: ["connect"]                  # add "--serve", "svc1" to serve; "-p", "svc:8080" to publish
    env:
      - name: OCTELIUM_DOMAIN
        value: <DOMAIN>
      - name: OCTELIUM_AUTH_TOKEN
        valueFrom:
          secretKeyRef: { name: <K8S_SECRET>, key: data }
    securityContext:
      capabilities:
        add: ["NET_ADMIN"]             # add "MKNOD" when forcing the TUN implementation
```

Replicas that serve the same Service are load balanced. For assertion auth, use
`octelium connect --assertion k8s` with a WORKLOAD User whose identity `identifier` is the
service account subject `system:serviceaccount:<ns>:<sa>` for an `oidcIdentityToken`
IdentityProvider that trusts the Kubernetes issuer.

Docs: https://octelium.com/docs/octelium/latest/user/cli/connect.md (Containers, Kubernetes)

## Helm chart

Chart `oci://ghcr.io/octelium/helm-charts/octelium` (values reorganized in chart v1.0.0).

```bash
# Token from an existing Kubernetes secret (preferred over --set octelium.auth.token)
helm install octelium-connector oci://ghcr.io/octelium/helm-charts/octelium \
  --set octelium.domain=<DOMAIN> \
  --set octelium.auth.existingSecret=<K8S_SECRET> [--set octelium.auth.existingSecretKey=<KEY>]

# Secretless: projected service-account token as an assertion
helm install octelium-connector oci://ghcr.io/octelium/helm-charts/octelium \
  --set octelium.domain=<DOMAIN> \
  --set serviceAccount.name=octelium-connector \
  --set octelium.auth.assertion.enabled=true \
  --set octelium.auth.assertion.audience=<IDP_AUDIENCE>

# Serve Services from this Kubernetes cluster
  --set "octelium.serve={svc1,svc2}"      # or --set octelium.serveAll=true; replicaCount=N to scale
```

Values set with `--set` are stored in the Helm release metadata; don't pass real tokens that way
outside quick trials. Other values: `octelium.publish` with `service.enabled` (expose published
Services inside that Kubernetes cluster), `octelium.auth.scopes`, `octelium.network.ipMode`,
`octelium.dns.local.enabled`, `octelium.extraArgs`. Check the chart's `values.yaml` or
`helm show values oci://ghcr.io/octelium/helm-charts/octelium` before relying on a key.

Docs: https://octelium.com/docs/octelium/latest/management/guide/service/devops/octelium-helm-kubernetes.md

## GitHub Actions

```yaml
permissions:
  id-token: write                      # needed for the secretless assertion
steps:
  - uses: octelium/github-action@v2
    with:
      domain: example.com
      audience: https://example.com    # must equal the oidcIdentityToken IdentityProvider audience
      # auth-token: ${{ secrets.OCTELIUM_AUTH_TOKEN }}   # alternative to audience/assertion
      # scopes: |                       # optional least privilege
      #   service:postgres.db
      # publish: |                      # map Services to runner localhost ports
      #   postgres.db:5432
      # serve: |                        # serve Services from the runner
      #   preview-app
      # version: "0.43.0"               # pin the client
  - run: curl http://demo-nginx
  - if: always()
    uses: octelium/github-action@v2
    with:
      domain: example.com
      command: logout
```

The User's identity for GitHub assertions is the token `sub`, e.g.
`repo:<ORG>/<REPO>:ref:refs/heads/<BRANCH>`. Forked-PR workflows don't receive repository
secrets, another reason to prefer assertions. `extra-args` rejects `--detach`, `--domain`,
`--auth-token`, `--assertion`, `--homedir`. `command: install` with `components:` installs
`octeliumctl` for management workflows.

Docs: https://octelium.com/docs/octelium/latest/management/guide/service/devops/github-action.md

## Headless Linux servers (systemd)

`octelium connect -d --auth-token ...` starts a transient `systemd-run` unit as root with
`Restart=on-failure`. For a permanent service, use the packaged daemon or a unit that runs
`octelium connect` with `OCTELIUM_DOMAIN` and `OCTELIUM_AUTH_TOKEN` supplied from a root-only
environment file. Don't write tokens into world-readable unit files.

## Hygiene for ephemeral runners

- Use `--logout` (or `OCTELIUM_LOGOUT=true`) or an explicit `octelium logout` at the end so
  Sessions don't pile up against the User's `maxPerUser` limit.
- Use one-time or short-lived Credentials (`--one-time`, `--expire-in`) for bootstrap
  tokens; see the octelium-management skill.
- Narrow Sessions with `--scope` when the job only needs a few Services.
