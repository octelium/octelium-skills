# Running `octops init`, verifying, DNS, TLS, first login

Docs: https://octelium.com/docs/octelium/latest/install/cluster/installing-cluster.md

## Command

```bash
OCTELIUM_AUTH_TOKEN_SAVE_PATH=<private-new-file> OCTELIUM_SKIP_MESSAGES=true \
  octops init <DOMAIN> --bootstrap <file|-> \
  [--kubeconfig <path>] [--kubecontext <ctx>] [--version <v>]
```

- Default kubeconfig: `$KUBECONFIG`, else `$HOME/.kube/config`. Always pass the intended
  context explicitly.
- `--version` defaults to `latest`; pin a version for reproducible installs.
- Create the token destination with `umask 077` and `mktemp` before init, as in SKILL.md;
  report its path only. Don't overwrite an existing credential file or print its contents.
- Environment variables read by `octops init` (v0.51.0):

  | Variable | Effect |
  | --- | --- |
  | `OCTELIUM_REGION_EXTERNAL_IP=<ip>` | Use this address as the Region/Ingress external IP (single public node without a cloud LB) |
  | `OCTELIUM_AUTH_TOKEN_SAVE_PATH=<file>` | Also write the initial token to this file (dir 0700, file 0600) |
  | `OCTELIUM_SKIP_MESSAGES=true` | Don't print the completion messages and the `octelium login ... --auth-token` line |

  CNI conf dir, front proxy and SPIFFE are Bootstrap fields since v0.40.0 (bootstrap.md).

## What it does

1. Validates the Bootstrap, asks for confirmation (skipped when stdin isn't a terminal).
2. Checks for an existing completed installation and refuses it. Stores the domain, Region and
   Bootstrap in `default/octelium-init`, or checks the existing input before resuming.
3. Runs the Genesis job `octelium-genesis` in the `default` namespace, which: waits for nodes;
   taints dedicated data-plane nodes with `octelium.com/gateway-init`; creates the `octelium`
   namespace if needed; checkpoints Cluster identity in `octelium/octelium-genesis-init`;
   claims the datastores for this initialization without truncating resources or flushing Redis;
   creates missing ClusterConfig, Region, Namespaces, system Services, built-in Policies,
   `root` User and `root-init` Credential; deploys the components.
4. Tracks the submitted Job and its Pods, reports failures and waits for installation readiness
   and `octelium/init-token`, then saves the token to the configured file. Without
   `OCTELIUM_SKIP_MESSAGES=true`, it also prints the token-bearing login command.

This describes v0.50.0 and later with matching `octops` and Genesis versions. Earlier Genesis
deletes/re-creates the namespace, truncates the resource table and flushes Redis. Upgrade the
CLI before targeting a current release; `--version` controls the Genesis image, not the CLI.

## Resuming an interrupted initialization (v0.50.0+)

Inspect the existing Job, Pods and events first; a local timeout does not stop Genesis. Keep
the domain, Region/external-IP settings, Bootstrap and datastore Secret values unchanged.
When the existing Job has stopped and its cause is fixed, retry the same command with the same
target version. Genesis resumes from its checkpoint and preserves the initialization's
identity, resources and encryption key material. Do not run two operations concurrently.

A completed installation is rejected with `Use octops upgrade instead of init`. A Bootstrap
or storage identity mismatch is a reason to stop and inspect the original input, not to delete
the initialization Secret, namespace, locks or database contents. Correcting Bootstrap input
is supported only before initialization has claimed storage; do not assume an arbitrary edit
is safe after a partial run. An old interrupted initialization without current checkpoints
needs separate recovery; upgrading the CLI does not make that old state resumable.

## Verify

```bash
kubectl -n default get job octelium-genesis
kubectl -n default logs job/octelium-genesis --tail=100
kubectl -n octelium get pods -o wide            # all Running/Ready
kubectl -n octelium get ds                       # Gateway Agent on each data-plane node
kubectl -n octelium get svc octelium-ingress-dataplane   # EXTERNAL-IP or hostname must be set
kubectl get nodes -o custom-columns=NAME:.metadata.name,TAINTS:.spec.taints   # gateway-init removed once Gateways are ready
```

After logging in: `octeliumctl get gw -o yaml` shows each Gateway's `status.publicIPs` (must be
the public addresses clients can reach) and `status.hostname`.

## Public DNS

| Type | Name | Value |
| --- | --- | --- |
| `A` (or `AAAA`) | `<DOMAIN>` | Ingress external IP |
| `CNAME` | `*.<DOMAIN>` | `<DOMAIN>` |

If the load balancer exposes a hostname instead of an IP (e.g. AWS NLB/ELB), point `<DOMAIN>` at it
with the DNS provider's ALIAS/ANAME/flattened-CNAME feature and keep `*.<DOMAIN>` as a CNAME.
Non-default Namespaces with public Services need `*.<NAMESPACE>.<DOMAIN>` → `<DOMAIN>`.
QUIC (if enabled): an `A`/`AAAA` record per Gateway `status.hostname` → its public IP.

## TLS certificate

Required SANs: `<DOMAIN>`, `*.<DOMAIN>`, `*.local.<DOMAIN>` (recommended). The certificate must
end up in the Kubernetes TLS Secret `cert-cluster` in namespace `octelium` (watched by the Cluster).
Per-Namespace certificates: Secret `cert-ns-<NAMESPACE>` with `*.<NAMESPACE>.<DOMAIN>` and
`*.<NAMESPACE>.local.<DOMAIN>`.

Recommended for production: cert-manager with a DNS-01 solver.

```yaml kubernetes
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: octelium-cluster
  namespace: octelium
spec:
  secretName: cert-cluster
  issuerRef:
    name: <CLUSTER_ISSUER>          # an ACME ClusterIssuer with a dns01 solver for your provider
    kind: ClusterIssuer
  dnsNames:
    - <DOMAIN>
    - "*.<DOMAIN>"
    - "*.local.<DOMAIN>"
```

Create the Certificate after init. Older Genesis versions delete/re-create the namespace. Manual
alternative: `octops cert <DOMAIN> --cert fullchain.pem --key privkey.pem [--kubeconfig ...]`
(`--namespace <ns>` for a Namespace certificate). Details and rotation: octelium-cluster-ops.

Until the certificate is in place, CLI logins need `OCTELIUM_INSECURE_TLS=true` for that command
only.

## First login and handover

1. Give the user the token file path (from `OCTELIUM_AUTH_TOKEN_SAVE_PATH`). The token is also
   retrievable by anyone who can read `octelium/init-token` in Kubernetes while the `root-init`
   Credential exists.
2. With v0.51.0+, the user logs in:
   `octelium login --domain <DOMAIN> --auth-token-file <private-file>`.
   For another machine, transfer it privately to a mode-0600 file there first.
   Older clients use `OCTELIUM_AUTH_TOKEN="$(cat <private-file>)" octelium login --domain <DOMAIN>`.
3. Create named admins, an IdentityProvider and access Policies, then delete `root-init`
   (octelium-management skill). Delete the token file afterwards.
4. Optional: deploy an OpenTelemetry collector as `octelium-collector` in `octelium` for access
   logs; plan backups of PostgreSQL; record the installed version (`octops upgrade <DOMAIN> --check`
   shows available upgrades).
