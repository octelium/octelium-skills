# TLS certificates

Docs: https://octelium.com/docs/octelium/latest/install/cluster/tls-certificate.md

## What the Cluster needs

| Secret (namespace `octelium`) | SANs | Used for |
| --- | --- | --- |
| `cert-cluster` | `<DOMAIN>`, `*.<DOMAIN>`, `*.local.<DOMAIN>` (recommended), optionally `*.default.<DOMAIN>`, `*.default.local.<DOMAIN>` | API server, Auth server, Portal, public and TLS Services in the `default` Namespace |
| `cert-ns-<NAMESPACE>` | `*.<NAMESPACE>.<DOMAIN>`, `*.<NAMESPACE>.local.<DOMAIN>` | Public (`isPublic`) or TLS (`isTLS`) Services in that Namespace |

The Cluster watches these Kubernetes TLS Secrets and syncs them into Octelium automatically.
A fresh Cluster uses a self-signed certificate until `cert-cluster` is provided. Wildcard
certificates from Let's Encrypt require DNS-01 validation.

## Install or rotate manually

```bash
octops cert <DOMAIN> --cert /path/fullchain.pem --key /path/privkey.pem [--kubeconfig <path>] [--kubecontext <ctx>]
octops cert <DOMAIN> --namespace production --cert ns-fullchain.pem --key ns-privkey.pem
# equivalent with kubectl (create or replace):
kubectl -n octelium create secret tls cert-cluster --cert fullchain.pem --key privkey.pem --dry-run=client -o yaml | kubectl apply -f -
```

Use the full chain (leaf + intermediates). Aliases: `octops cert`, `crt`, `certificate`.

## Automate renewal

Preferred: cert-manager in the same Kubernetes cluster with an ACME `ClusterIssuer` using a DNS-01
solver for the user's DNS provider (Cloudflare, Route 53, Cloud DNS, Azure DNS, ...), and:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: octelium-cluster
  namespace: octelium
spec:
  secretName: cert-cluster
  issuerRef:
    name: <CLUSTER_ISSUER>
    kind: ClusterIssuer
  dnsNames:
    - <DOMAIN>
    - "*.<DOMAIN>"
    - "*.local.<DOMAIN>"
```

Add one `Certificate` per Namespace that needs its own (`secretName: cert-ns-<NAMESPACE>`).
The DNS provider API token for the solver is a Kubernetes Secret in cert-manager's namespace; the
user supplies it, never paste it into files you commit.

Alternative on quick-install hosts: certbot with the provider's DNS plugin and a deploy hook, e.g.
`/etc/letsencrypt/renewal-hooks/deploy/octelium.sh`:

```bash
#!/bin/sh
octops cert <DOMAIN> --cert "$RENEWED_LINEAGE/fullchain.pem" --key "$RENEWED_LINEAGE/privkey.pem" \
  --kubeconfig /etc/rancher/k3s/k3s.yaml < /dev/null
```

(stdin from `/dev/null` keeps `octops` non-interactive.) Test with `certbot renew --dry-run`.

## Inspect without exposing keys

```bash
kubectl -n octelium get secret cert-cluster -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl x509 -noout -subject -issuer -enddate -ext subjectAltName
echo | openssl s_client -connect <DOMAIN>:443 -servername <DOMAIN> 2>/dev/null \
  | openssl x509 -noout -issuer -enddate -ext subjectAltName
```

(`openssl x509 -ext` needs OpenSSL 1.1.1+.) Behind a front proxy, the public certificate lives on
the proxy, not in `cert-cluster`.

## Symptoms

- Clients report `x509: certificate signed by unknown authority`: still the self-signed
  certificate, or an incomplete chain.
- Works for `<DOMAIN>` but not `svc.<DOMAIN>`: missing `*.<DOMAIN>` SAN.
- Public Service in Namespace `prod` fails TLS: missing `cert-ns-prod`.
- Expired: renew and re-run `octops cert` (or fix the cert-manager `Certificate`/`Order`/
  `Challenge` status: `kubectl describe certificate -n octelium`).
