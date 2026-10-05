# Secrets, Configs and ClusterConfig

## Secrets

Docs: https://octelium.com/docs/octelium/latest/management/core/secret.md

Secrets hold values that other resources reference by name (`fromSecret: <name>`): upstream
passwords, API keys, private keys, kubeconfigs, IdP client secrets, mTLS client certificates.
The API never returns Secret data (`get secret` shows metadata only), and by default the
Cluster stores it unencrypted in its database like other resources (encryption at rest needs a
custom secret-manager plugin or the Enterprise package).

Create them so the value never passes through the agent, the shell history or a Git tree:

| Situation | Command |
| --- | --- |
| Human at a terminal (preferred) | user runs `octeliumctl create secret <name>` and types the value at the prompt |
| Value already in a file (keys, kubeconfigs) | `octeliumctl create secret <name> --file /path/to/file` |
| Value in an environment variable (CI) | `octeliumctl create secret <name> --from-env VAR` |
| From another command | `some-command \| octeliumctl create secret <name> -f -` |
| TLS certificate + key | `octeliumctl create secret <name> --cert chain.pem --cert-key key.pem` |
| Rotate | same flags with `octeliumctl update secret <name>` |
| Delete | `octeliumctl delete secret <name>` (check nothing references it first) |

Avoid `--value <secret>`: it lands in the process list and shell history. Without a TTY (agent
shells), the interactive prompt is unavailable and the CLI requires `--value`, `--file`,
`--from-env` or `-f -`; hand the command to the user instead of passing the value yourself.

Declarative Secrets (`kind: Secret` with `data.value`) are applied only with `--include-secret`
and are always re-sent on apply. Keep such files encrypted and outside the main config tree.

## Configs

`kind: Config` (and `octeliumctl create|update|get|delete config`) stores **non-sensitive** data:
`data.value`, `data.valueBytes`, `data.dataMap.map`, or structured `data.attrs`. It is applied
by default. Use Secrets, not Configs, for anything sensitive. Schema:
https://octelium.com/schemas/octelium/latest/core.v1.Config.schema.json

## ClusterConfig

Docs: https://octelium.com/docs/octelium/latest/management/core/cluster-config.md
Schema: https://octelium.com/schemas/octelium/latest/core.v1.ClusterConfig.schema.json

One resource with Cluster-wide settings. `octeliumctl get cc -o yaml` shows it (it is named
`default` on current Clusters; the name in your file is ignored). Applying a ClusterConfig
document **replaces the whole spec**, so always start from the exported YAML:

```bash
octeliumctl get cc -o yaml > cluster-config.yaml
# edit only the requested section
octeliumctl validate cluster-config.yaml
octeliumctl apply --dry-run cluster-config.yaml
uv run scripts/plan_apply.py cluster-config.yaml     # shows every changed/reset ClusterConfig field
octeliumctl apply cluster-config.yaml
```

Check the installed CLI's help first. On versions without native validation/dry-run, use
`validate_resources.py` and `plan_apply.py` instead (apply-workflow.md).

Sections:

| Path | Purpose |
| --- | --- |
| `spec.session.human` / `spec.session.workload` | `clientDuration`, `clientlessDuration`, `accessTokenDuration`, `refreshTokenDuration`, `maxPerUser`, `defaultState` (`ACTIVE`/`PENDING`/`REJECTED`) |
| `spec.device.human` / `spec.device.workload` | `maxPerUser`, `defaultState` for newly registered Devices |
| `spec.authorization` | Global `policies` and `inlinePolicies`, evaluated for every request |
| `spec.authentication.geolocation.mmdb` | MaxMind MMDB database (`upstream.url` or `fromConfig`) for GeoIP data in Sessions |
| `spec.authenticator` | Authenticator (MFA/passkey) behavior; see the Authenticators docs page and the schema |
| `spec.ingress` | `useForwardedForHeader`, `xffNumTrustedHops` (only behind a trusted proxy) |
| `spec.dns` | `fallbackZone.servers` (`dns://`, `udp://`, `tls://`) and `cacheDuration` for names outside the Cluster; `zones` |
| `spec.gateway.wireguardKeyRotationDuration` | Gateway WireGuard key rotation |

Durations are objects with one unit: `milliseconds`, `seconds`, `minutes`, `hours`, `days`, `weeks` or `months` (e.g. `{hours: 4}`).

Impact notes:

- Global DENY rules and `defaultState: PENDING` can cut off every User, including admins. Keep
  an admin path (e.g. a higher-priority ALLOW for the admin Group) and preview carefully.
- Shorter Session durations take effect at the next refresh.
- `useForwardedForHeader` without a trusted front proxy lets clients spoof their IP (and GeoIP).
