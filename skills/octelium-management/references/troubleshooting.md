# Management troubleshooting and visibility

## octeliumctl errors

| Output | Meaning | Action |
| --- | --- | --- |
| `Unknown field in the <Kind> Resource at <path>: ...` | Field not in this CLI's API; it was dropped | Fix the typo, or upgrade the CLI if the field is newer. Re-apply. |
| `Skipping the <Kind> <name>. Its kind is not included in this apply operation` | Kind filtered by `--include/--exclude`, Secret without `--include-secret`, or a kind apply doesn't manage | Adjust flags, or use the imperative command. |
| `Could not create <Kind> <name>. ...` / `Could not update ...` | Server-side validation failed (missing referenced Namespace/Secret/Policy, invalid value, reserved name) | Other resources were still applied. Fix and re-apply; re-run `plan_apply.py` to see the new state. |
| `The ClusterConfig Resource is defined more than once` | Two ClusterConfig documents in the paths | Keep one. |
| `Could not find any Resources in: ...` | No YAML documents found | Check paths and extensions (`.yaml`/`.yml`). |
| `Invalid Resource kind: X` | `--include/--exclude` value isn't an apply kind | Use `Secret, Config, Policy, IdentityProvider, Namespace, Group, User, Service, Credential`. |
| `The value must be set via one of the flags: --value, --file or --from-env` | `create secret/config` without a TTY | Let the user run it interactively, or use `--file`/`--from-env`/`-f -`. |
| `PermissionDenied` / `Unauthorized` | Your Session's Policies don't allow that API call | You lack admin rights on this Cluster; ask an admin. Don't try other identities' tokens. |
| `Unavailable` / name resolution / x509 errors | Connectivity to the Cluster | See the octelium-connect troubleshooting reference. |
| `Invalid name: ...` | Name segment violates `^[a-z][a-z0-9-]{0,38}[a-z0-9]$` or has `--` | Rename. |

## Service created but not working

1. `octeliumctl get svc <name> -o yaml`: check `status` (addresses, Namespace) and that the spec
   is what you intended (fields you omitted were reset).
2. Upstream reachability: for Cluster-reachable upstreams, from inside the Kubernetes cluster;
   for `upstream.user` upstreams, the serving User must be connected with
   `--serve <svc>[.<ns>]` (`octeliumctl get sess --user <u>` shows connected Sessions).
3. `fromSecret` names exist (`octeliumctl get sec`); IdP/upstream credentials are valid.
4. Managed containers: Kubernetes-side logs are in the `octelium` namespace (octelium-cluster-ops).
5. Public Services: DNS for `*.<ns>.<DOMAIN>` and a certificate covering it (octelium-cluster-ops).
6. Access: follow "Diagnosing access denied" in policies.md.

## Visibility and access logs

Docs: https://octelium.com/docs/octelium/latest/management/core/visibility.md

- Every Service emits OpenTelemetry access logs (`kind: AccessLog`) with the Session/User/
  Device, the Service/Namespace, L7 details, `status` (`ALLOWED`/`DENIED`) and
  `reason.details.policyMatch` (the Policy or inline Policy that decided).
- Logs and metrics are exported to an OTLP gRPC receiver that must be reachable as the
  Kubernetes Service `octelium-collector` in the `octelium` namespace on port `8080`. Without it,
  nothing is stored. Deploying the collector (e.g. the OpenTelemetry Helm chart with
  `fullnameOverride: octelium-collector`) is a Kubernetes task; see the docs page for a working
  values file.
- `octeliumctl` has no log-query command; use the collector's backend (Grafana/Loki, Elastic,
  Splunk, ...).

## Reporting back

When you can't finish a change, report: what you inspected, the exact error lines, what was
applied (apply may have partially succeeded), and the state that remains.
