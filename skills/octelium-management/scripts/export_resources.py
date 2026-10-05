#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6"]
# ///
"""Export complete, apply-ready configuration with read-only `octeliumctl get` calls.

    uv run scripts/export_resources.py --domain example.com > resources.yaml
    uv run scripts/export_resources.py --include Service,Namespace --skip-cluster-config

Every list page is read. System resources and server-managed fields are omitted. The default
kinds are Config, Policy, IdentityProvider, Namespace, Group, User and Service, plus the
ClusterConfig singleton. Secret values and Credential tokens cannot be recovered this way.
This is a configuration export, not a datastore backup. Protect the output: Configs and
resource attributes may contain sensitive data. No output is written until all reads succeed.

Exit status: 0 exported, 2 usage/environment problems.
"""

from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import DEFAULT_KINDS, report_error, resolve_kinds, yaml
from plan_apply import CtlError, META_KEYS, list_resources, run_ctl

EXPORT_KINDS = [k for k in DEFAULT_KINDS if k != "Credential"]


def portable_resource(kind: str, resource: dict[str, Any]) -> dict[str, Any] | None:
    metadata = resource.get("metadata", {})
    if not isinstance(metadata, dict):
        raise CtlError(f"invalid {kind} metadata")
    if kind != "ClusterConfig" and (metadata.get("isSystem") or metadata.get("isSystemHidden")):
        return None
    name = metadata.get("name", "default" if kind == "ClusterConfig" else "")
    if not isinstance(name, str) or not name:
        raise CtlError(f"invalid {kind} metadata.name")
    spec = resource.get("spec", {})
    if spec is None:
        spec = {}
    if not isinstance(spec, dict):
        raise CtlError(f"invalid {kind} spec")
    result = {"kind": kind, "metadata": {"name": name, **{k: metadata[k] for k in META_KEYS if k in metadata}},
              "spec": spec}
    if kind == "Config" and "data" in resource:
        result["data"] = resource["data"]
    return copy.deepcopy(result)


def export_resources(ctl: str, domain: str | None, kinds: list[str], cluster_config: bool) -> list[dict[str, Any]]:
    documents = []
    for kind in kinds:
        for resource in list_resources(ctl, domain, kind):
            document = portable_resource(kind, resource)
            if document is not None:
                documents.append(document)
    if cluster_config:
        documents.append(portable_resource("ClusterConfig", run_ctl(ctl, domain, ["get", "clusterconfig"])))
    return documents


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--include", action="append", help="restrict kinds, repeatable or comma-separated; excludes Secret/Credential")
    ap.add_argument("--exclude", action="append", help="omit kinds, repeatable or comma-separated")
    ap.add_argument("--skip-cluster-config", action="store_true", help="omit the ClusterConfig singleton")
    ap.add_argument("--domain", help="Cluster domain (default: OCTELIUM_DOMAIN)")
    ap.add_argument("--octeliumctl", default="octeliumctl", help="path to the octeliumctl binary")
    args = ap.parse_args()
    try:
        kinds = resolve_kinds(args.include or EXPORT_KINDS, args.exclude, False)
        if any(k not in EXPORT_KINDS for k in kinds):
            raise ValueError("configuration export does not include Secret or Credential")
        ctl = shutil.which(args.octeliumctl) or (args.octeliumctl if os.access(args.octeliumctl, os.X_OK) else None)
        if not ctl:
            raise CtlError("octeliumctl not found; install the Octelium CLIs first")
        if not (args.domain or os.environ.get("OCTELIUM_DOMAIN")):
            raise CtlError("set --domain or OCTELIUM_DOMAIN")
        documents = export_resources(ctl, args.domain, kinds, not args.skip_cluster_config)
        output = yaml.safe_dump_all(documents, sort_keys=False, explicit_start=True)
    except (CtlError, OSError, ValueError, yaml.YAMLError) as err:
        report_error(err, False)
        return 2
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
