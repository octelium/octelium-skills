# Bootstrap file

Docs: https://octelium.com/docs/octelium/latest/install/cluster/bootstrap.md

The Bootstrap is the only input of `octops init` besides the domain. It is read from
`--bootstrap <file>` (or `--bootstrap -` for stdin) and stored by `octops init` in the Kubernetes
Secret `default/octelium-init`. There is no published JSON Schema for it; the field list below
comes from the `octelium.api.cluster.bootstrap.v1.Config` message (v0.43.0).

## Fields

```yaml
spec:
  primaryStorage:
    postgresql:                  # required
      host: <host>               # required (hostname or IP)
      port: 5432                 # optional
      username: <user>           # required
      password: <password>       # one of password | passwordFromSecret is required
      passwordFromSecret:
        name: <k8s-secret>
        namespace: <k8s-namespace>
        key: <key>
      database: octelium
      isTLS: true
  secondaryStorage:
    redis:                       # required (Redis or Valkey)
      host: <host>               # required
      port: 6379
      username: <user>           # optional (ACL user)
      password: <password>       # one of password | passwordFromSecret is required
      passwordFromSecret: {name: ..., namespace: ..., key: ...}
      database: 0                # dedicated index: it is flushed at init
      isTLS: true
  network:                       # optional
    mode: DUAL_STACK             # DEFAULT (= DUAL_STACK) | DUAL_STACK | V4_ONLY | V6_ONLY
    v4:
      clusterNetwork: 100.64.0.0/10
    v6:
      clusterNetwork: <fd00::/8 subrange>   # generated when unset
    wireguard:
      gatewayPort: 53820
      mtu: 1280
    quicv0:                      # experimental
      enable: false
      gatewayPort: 8443
      mtu: 1280
  cni:                           # v0.40.0+; set at most one
    confDir: /var/lib/rancher/k3s/agent/etc/cni     # Multus dir = <confDir>/multus/net.d
    # multusConfDir: /etc/cni/multus/net.d          # explicit Multus delegate conf dir
  ingress:                       # v0.40.0+
    frontProxy:
      enable: false              # true when an external L7 proxy terminates TLS
  spiffe:                        # v0.40.0+
    enable: false
    trustDomain: example.com     # optional
    csiDriver:
      name: csi.spiffe.io        # optional; default csi.spiffe.io
```

`network.v4.gatewayBits` and `regionBits` also exist; leave them unset unless the docs say
otherwise. Only include sections you need: every omitted field takes its default.

`octops init` rejects the file before installing when: `primaryStorage.postgresql` or
`secondaryStorage.redis` is missing; a host or the PostgreSQL username is empty or invalid;
neither `password` nor `passwordFromSecret` is set (or `password` is empty); a port is invalid.

## Minimal production example (secrets by reference)

```yaml
spec:
  primaryStorage:
    postgresql:
      host: octelium-rw.octelium-dbs.svc
      port: 5432
      username: octelium
      database: octelium
      passwordFromSecret:
        name: octelium-postgres
        namespace: octelium-dbs
        key: password
      isTLS: false          # in-cluster traffic; use true for external/managed databases
  secondaryStorage:
    redis:
      host: valkey-primary.octelium-dbs.svc
      port: 6379
      username: default
      passwordFromSecret:
        name: octelium-redis
        namespace: octelium-dbs
        key: password
      database: 0
      isTLS: false
```

Create the referenced Kubernetes Secrets without echoing values, e.g. with the user typing them:

```bash
kubectl -n octelium-dbs create secret generic octelium-postgres --from-file=password=/dev/stdin
```

Don't put the Secrets in the `octelium` namespace: init deletes and re-creates that namespace.

## Version notes

| Setting | v0.40.0 and later | Before v0.40.0 |
| --- | --- | --- |
| Multus/CNI conf dir | `spec.cni.confDir` / `spec.cni.multusConfDir` | `OCTELIUM_CNI_CONF_DIR` env on `octops init` |
| Front proxy | `spec.ingress.frontProxy.enable` (persisted) | `OCTELIUM_FRONT_PROXY_MODE=true` on init **and every upgrade** |
| SPIFFE | `spec.spiffe.*` (persisted) | `OCTELIUM_ENABLE_SPIFFE_CSI`, `OCTELIUM_SPIFFE_CSI_DRIVER`, `OCTELIUM_SPIFFE_TRUST_DOMAIN` on init and every upgrade |

Current docs pages may still show the environment variables; `octops` v0.40.0+ no longer reads
them. These settings are captured once at `octops init`; there is no command to change them
afterwards.

## Handling the file

- Treat it as a secret when it contains inline passwords; prefer `passwordFromSecret`.
- Don't commit it with inline passwords; delete temporary copies after install.
- Everything in it is visible to anyone who can read Secrets in the `default` namespace
  (`octelium-init`). Restrict RBAC accordingly.
