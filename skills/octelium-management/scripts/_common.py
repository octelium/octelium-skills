"""Shared helpers for the octelium-management scripts.

Loading and kind selection follow `octeliumctl apply`:
- arguments are files or directories (searched recursively for *.yaml/*.yml) or "-" for stdin;
- every YAML document must carry `kind`;
- default kinds are Config, Policy, IdentityProvider, Namespace, Group, User, Service, Credential;
  Secret only with --include-secret; ClusterConfig is always applied when present;
- current system resources are excluded from the apply comparison; remove them from exports.
"""

from __future__ import annotations

import csv
import json
import os
import re
import stat
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
KNOWN_KINDS = set(SUPPORTED_KINDS) | NON_APPLY_KINDS | {"ClusterConfig"}

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
        kind = self.body.get("kind")
        metadata = self.body.get("metadata")
        name = metadata.get("name") if isinstance(metadata, dict) else None
        self.kind = kind if isinstance(kind, str) else ""
        self.name = name if isinstance(name, str) else ""

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


class InputError(ValueError):
    pass


class ResourceLoader(yaml.SafeLoader):
    pass


ResourceLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in resolvers
          if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
ResourceLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def construct_mapping(loader: ResourceLoader, node: Any, deep: bool = False) -> dict[str, Any]:
    seen = set()
    for key_node, _ in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            key = "<<"
        else:
            key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, "mapping keys must be strings", key_node.start_mark)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


ResourceLoader.add_constructor("tag:yaml.org,2002:map", construct_mapping)


def _yaml_files(path: str) -> list[str]:
    mode = os.stat(path).st_mode
    if stat.S_ISDIR(mode):
        if os.path.islink(path):
            return []
        found = []
        def fail(err: OSError) -> None:
            raise err
        for root, _dirs, files in os.walk(path, onerror=fail):
            for f in files:
                candidate = os.path.join(root, f)
                if f.lower().endswith((".yaml", ".yml")) and stat.S_ISREG(os.lstat(candidate).st_mode):
                    found.append(candidate)
        return sorted(found)
    if stat.S_ISREG(mode):
        return [path]
    raise OSError(f"the path {path} is neither a regular file nor a directory")


def load_documents(paths: list[str]) -> list[Doc]:
    docs: list[Doc] = []
    for arg in paths:
        sources = ["-"] if arg == "-" else _yaml_files(arg)
        for src in sources:
            if src == "-":
                text = sys.stdin.read()
            else:
                with open(src, encoding="utf-8") as stream:
                    text = stream.read()
            try:
                bodies = list(yaml.load_all(text, Loader=ResourceLoader))
            except yaml.YAMLError as err:
                raise InputError(f"{src}: invalid YAML: {err}") from err
            for idx, body in enumerate(bodies, start=1):
                if body is None:
                    continue
                if not isinstance(body, dict):
                    raise InputError(f"{src} (document {idx}): expected a mapping, got {type(body).__name__}")
                try:
                    json.dumps(body, allow_nan=False)
                except (TypeError, ValueError, RecursionError) as err:
                    raise InputError(f"{src} (document {idx}): resource cannot be represented as JSON: {err}") from err
                docs.append(Doc(src, idx, body))
    if not docs:
        raise InputError(f"could not find any resources in: {', '.join(paths)}")
    return docs


def resource_errors(docs: list[Doc]) -> list[list[str]]:
    results = []
    seen: dict[tuple[str, str], str] = {}
    for doc in docs:
        errors = []
        if not doc.kind:
            errors.append("kind must be a non-empty string")
        elif doc.kind not in KNOWN_KINDS:
            errors.append(f"unknown kind {doc.kind!r}")
        metadata = doc.body.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            errors.append("metadata must be a mapping")
        if doc.kind != "ClusterConfig" and not doc.name:
            errors.append("metadata.name must be a non-empty string")
        elif isinstance(metadata, dict) and "name" in metadata and not isinstance(metadata["name"], str):
            errors.append("metadata.name must be a string")
        if doc.body.get("spec") is not None and not isinstance(doc.body["spec"], dict):
            errors.append("spec must be a mapping")
        if doc.kind and (doc.name or doc.kind == "ClusterConfig"):
            key = (doc.kind, "" if doc.kind == "ClusterConfig" else doc.full_name)
            if key in seen:
                errors.append(f"duplicate {doc.kind} {doc.full_name!r} (also in {seen[key]})")
            else:
                seen[key] = doc.where
        results.append(errors)
    return results


def report_error(err: Exception, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"errors": [str(err)]}, indent=2))
    else:
        print(f"error: {err}", file=sys.stderr)


def resolve_kinds(include: list[str] | None, exclude: list[str] | None, include_secret: bool) -> list[str]:
    try:
        include = [k for value in include or [] for k in next(csv.reader([value], strict=True))]
        exclude = [k for value in exclude or [] for k in next(csv.reader([value], strict=True))]
    except csv.Error as err:
        raise ValueError(f"invalid kind selection: {err}") from err
    for k in (include or []) + (exclude or []):
        if k not in SUPPORTED_KINDS:
            raise ValueError(f"invalid resource kind {k!r}; supported: {', '.join(SUPPORTED_KINDS)}")
    inc = list(include) if include else list(DEFAULT_KINDS)
    if include_secret and "Secret" not in inc:
        inc.insert(0, "Secret")
    return [k for k in SUPPORTED_KINDS if k in inc and k not in (exclude or [])]
