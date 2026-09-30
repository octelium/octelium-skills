"""Shared helpers for the octelium-management scripts.

Loading and kind selection mirror `octeliumctl apply` (octelium v0.43.0):
- arguments are files or directories (searched recursively for *.yaml/*.yml) or "-" for stdin;
- every YAML document must carry `kind`;
- default kinds are Config, Policy, IdentityProvider, Namespace, Group, User, Service, Credential;
  Secret only with --include-secret; ClusterConfig is always applied when present;
- resources with metadata.isSystem are never created, updated or pruned by apply.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on hosts without PyYAML
    sys.stderr.write(
        "error: PyYAML is required. Run this script with `uv run <script>` (dependencies are declared\n"
        "inline), or install them with `python3 -m pip install pyyaml jsonschema`.\n"
    )
    sys.exit(2)

SUPPORTED_KINDS = [
    "Secret",
    "Config",
    "Policy",
    "IdentityProvider",
    "Namespace",
    "Group",
    "User",
    "Service",
    "Credential",
]
DEFAULT_KINDS = [k for k in SUPPORTED_KINDS if k != "Secret"]

# Kinds that exist in the API but that `octeliumctl apply` skips with a warning.
NON_APPLY_KINDS = {"Session", "Device", "Authenticator", "Gateway", "Region", "AccessLog", "ComponentLog", "PolicyTrigger"}

# `octeliumctl get <cmd>` for each kind.
GET_COMMAND = {
    "Secret": "secret",
    "Config": "config",
    "Policy": "policy",
    "IdentityProvider": "identityprovider",
    "Namespace": "namespace",
    "Group": "group",
    "User": "user",
    "Service": "service",
    "Credential": "credential",
}

# Created by the Cluster installer but NOT marked as system resources, so `apply --prune`
# deletes them when they are missing from the desired state.
INSTALL_BUILTINS = {
    ("User", "root"): "initial User; the root-init token and possibly your only admin Session belong to it",
    ("Credential", "root-init"): "initial authentication token for the root User",
    ("Policy", "allow-all"): "built-in Policy commonly attached to admins",
    ("Policy", "deny-all"): "built-in Policy",
    ("Policy", "octelium-api-full-access"): "built-in Policy granting full Octelium API access",
    ("Policy", "octelium-api-read-only"): "built-in Policy granting read-only Octelium API access",
    ("Policy", "http-read-only"): "built-in Policy",
    ("Service", "demo-nginx.default"): "demo Service",
    ("Service", "essh.octelium"): "built-in embedded SSH Service used by `octelium ssh`/`octelium cp`",
    ("Service", "socks5.octelium"): "built-in embedded SOCKS5 Service",
}


@dataclass
class Doc:
    source: str
    index: int
    body: dict[str, Any]
    kind: str = field(init=False)
    name: str = field(init=False)

    def __post_init__(self) -> None:
        self.kind = str(self.body.get("kind", ""))
        self.name = str((self.body.get("metadata") or {}).get("name", ""))

    @property
    def where(self) -> str:
        return self.source if self.index <= 1 else f"{self.source} (document {self.index})"

    @property
    def full_name(self) -> str:
        return full_name(self.kind, self.name)


def full_name(kind: str, name: str) -> str:
    """Services in the default Namespace may be written without the `.default` suffix."""
    if kind == "Service" and name and "." not in name:
        return f"{name}.default"
    return name


def _yaml_files(path: str) -> list[str]:
    if os.path.isdir(path):
        found = []
        for root, _dirs, files in os.walk(path):
            for f in files:
                if f.endswith((".yaml", ".yml")):
                    found.append(os.path.join(root, f))
        return sorted(found)
    return [path]


def load_documents(paths: list[str]) -> list[Doc]:
    docs: list[Doc] = []
    for arg in paths:
        if arg != "-" and not os.path.exists(arg):
            raise SystemExit(f"error: no such file or directory: {arg}")
        sources = ["-"] if arg == "-" else _yaml_files(arg)
        for src in sources:
            text = sys.stdin.read() if src == "-" else open(src, encoding="utf-8").read()
            try:
                bodies = list(yaml.safe_load_all(text))
            except yaml.YAMLError as err:
                raise SystemExit(f"error: {src}: invalid YAML: {err}")
            for idx, body in enumerate(bodies, start=1):
                if body is None:
                    continue
                if not isinstance(body, dict):
                    raise SystemExit(f"error: {src} (document {idx}): expected a mapping, got {type(body).__name__}")
                docs.append(Doc(src, idx, body))
    if not docs:
        raise SystemExit(f"error: could not find any resources in: {', '.join(paths)}")
    return docs


def resolve_kinds(include: list[str] | None, exclude: list[str] | None, include_secret: bool) -> list[str]:
    for k in (include or []) + (exclude or []):
        if k not in SUPPORTED_KINDS:
            raise SystemExit(f"error: invalid resource kind {k!r}; supported: {', '.join(SUPPORTED_KINDS)}")
    inc = list(include) if include else list(DEFAULT_KINDS)
    if include_secret and "Secret" not in inc:
        inc.insert(0, "Secret")
    return [k for k in SUPPORTED_KINDS if k in inc and k not in (exclude or [])]
