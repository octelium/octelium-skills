#!/usr/bin/env bash
# Refresh the JSON Schema snapshot bundled with the octelium-management skill.
#
#   scripts/sync_schemas.sh                 # download the latest published schemas
#   scripts/sync_schemas.sh --from DIR      # copy from a local checkout (e.g. octelium-ws/app/schemas/octelium/latest)
#   scripts/sync_schemas.sh --check         # exit 1 if the snapshot differs from the published schemas
set -Eeuo pipefail

BASE_URL="${OCTELIUM_SCHEMA_BASE_URL:-https://octelium.com/schemas/octelium/latest}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${ROOT}/skills/octelium-management/assets/schemas"
KINDS=(AccessLog Authenticator ClusterConfig ComponentLog Config Credential Device Gateway Group
  IdentityProvider Namespace Policy PolicyTrigger Region Secret Service Session User)

FROM=""
CHECK=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="${2:?--from needs a directory}"; shift 2 ;;
    --check) CHECK=true; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

for kind in "${KINDS[@]}"; do
  f="core.v1.${kind}.schema.json"
  if [[ -n "$FROM" ]]; then
    cp "${FROM}/${f}" "${TMP}/${f}"
  else
    curl -fsSL --retry 3 -A "octelium-skills-sync (+https://github.com/octelium/octelium-skills)" \
      -o "${TMP}/${f}" "${BASE_URL}/${f}"
  fi
  python3 -m json.tool "${TMP}/${f}" >/dev/null
done

if $CHECK; then
  if diff -rq "$TMP" "$DEST" >/dev/null; then
    echo "schema snapshot is up to date"
    exit 0
  fi
  diff -rq "$TMP" "$DEST" || true
  echo "schema snapshot is stale: run scripts/sync_schemas.sh" >&2
  exit 1
fi

mkdir -p "$DEST"
rm -f "${DEST}"/core.v1.*.schema.json
cp "${TMP}"/*.json "$DEST/"
echo "updated ${#KINDS[@]} schemas in ${DEST#"$ROOT"/}"
