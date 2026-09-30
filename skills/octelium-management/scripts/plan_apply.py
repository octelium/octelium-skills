#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6"]
# ///
"""Preview what `octeliumctl apply` would change, without changing anything.

`octeliumctl apply` has no dry-run. This script reads the desired state from files, reads the
current state with read-only `octeliumctl get ... -o json` calls, and prints the resources that
apply would create, update (full spec replacement) and, with --prune, DELETE. Pass the same
flags you intend to give to `octeliumctl apply`:

    uv run scripts/plan_apply.py ./octelium/
    uv run scripts/plan_apply.py --prune --include Service --include Namespace ./octelium/
    python3 scripts/plan_apply.py --domain example.com svc.yaml --json

It needs a logged-in `octeliumctl` (same Session as `octelium`) with permission to list the
included kinds. Nothing is created, updated or deleted.

Exit status: 0 plan computed, 1 the plan contains deletions of install built-ins or would
delete every resource of a kind, 2 usage/environment problems.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (  # noqa: E402
    GET_COMMAND,
    INSTALL_BUILTINS,
    NON_APPLY_KINDS,
    load_documents,
    full_name,
    resolve_kinds,
)

META_KEYS = ("displayName", "labels", "description", "annotations", "tags", "picURL")


class CtlError(RuntimeError):
    pass


def run_ctl(ctl: str, domain: str | None, args: list[str]) -> Any:
    cmd = [ctl, *args, "-o", "json"]
    if domain:
        cmd += ["--domain", domain]
    env = dict(os.environ)
    env.pop("OCTELIUM_DEV", None)  # keep stdout pure JSON
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120,
                              stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired:
        raise CtlError(f"`{' '.join(cmd)}` timed out; is a browser login waiting? Log in first.")
    if proc.returncode != 0:
        raise CtlError(f"`{' '.join(cmd)}` failed: {(proc.stderr or proc.stdout).strip()}")
    start = proc.stdout.find("{")
    if start < 0:
        if re.search(r"\bNo \w+ found\b", proc.stdout + proc.stderr):
            return {"items": []}  # empty lists are printed as text, e.g. "No Configs found"
        raise CtlError(f"`{' '.join(cmd)}` returned no JSON: {proc.stdout.strip()[:300]}")
    return json.loads(proc.stdout[start:])


def list_current(ctl: str, domain: str | None, kind: str) -> dict[str, dict[str, Any]]:
    items: dict[str, dict[str, Any]] = {}
    page = 1
    while True:
        out = run_ctl(ctl, domain, ["get", GET_COMMAND[kind], "--page", str(page)])
        for itm in out.get("items") or []:
            md = itm.get("metadata") or {}
            if md.get("isSystem"):
                continue
            items[full_name(kind, md.get("name", ""))] = itm
        if not (out.get("listResponseMeta") or {}).get("hasMore"):
            return items
        page += 1


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(obj, dict):
        if not obj:
            return {prefix: {}} if prefix else {}
        out: dict[str, Any] = {}
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
        return out
    if isinstance(obj, list):
        if not obj:
            return {prefix: []}
        out = {}
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
        return out
    return {prefix: obj}


def spec_diff(desired: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    d = flatten({"spec": desired.get("spec") or {},
                 "metadata": {k: v for k, v in (desired.get("metadata") or {}).items() if k in META_KEYS}})
    c = flatten({"spec": current.get("spec") or {},
                 "metadata": {k: v for k, v in (current.get("metadata") or {}).items() if k in META_KEYS}})
    return {
        "added": sorted(k for k in d if k not in c),
        "changed": sorted(k for k in d if k in c and d[k] != c[k]),
        "reset": sorted(k for k in c if k not in d),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="the same files/directories (or -) you will pass to apply")
    ap.add_argument("--include", action="append", help="as in octeliumctl apply")
    ap.add_argument("--exclude", action="append", help="as in octeliumctl apply")
    ap.add_argument("--include-secret", action="store_true", help="as in octeliumctl apply")
    ap.add_argument("--prune", action="store_true", help="also compute deletions, as `apply --prune` would")
    ap.add_argument("--domain", help="Cluster domain (default: OCTELIUM_DOMAIN)")
    ap.add_argument("--octeliumctl", default="octeliumctl", help="path to the octeliumctl binary")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    ctl = shutil.which(args.octeliumctl) or (args.octeliumctl if os.access(args.octeliumctl, os.X_OK) else None)
    if not ctl:
        print("error: octeliumctl not found; install the Octelium CLIs first", file=sys.stderr)
        return 2
    if not (args.domain or os.environ.get("OCTELIUM_DOMAIN")):
        print("error: set --domain or OCTELIUM_DOMAIN", file=sys.stderr)
        return 2

    kinds = resolve_kinds(args.include, args.exclude, args.include_secret)
    docs = load_documents(args.paths)

    plan: dict[str, Any] = {"kinds": kinds, "prune": args.prune, "create": [], "update": [],
                            "unchanged": [], "delete": [], "skipped": [], "clusterConfig": None,
                            "dangers": []}
    desired: dict[str, dict[str, dict[str, Any]]] = {k: {} for k in kinds}
    cluster_config = None
    for doc in docs:
        if doc.kind == "ClusterConfig":
            if cluster_config is not None:
                print("error: ClusterConfig is defined more than once", file=sys.stderr)
                return 2
            cluster_config = doc.body
        elif doc.kind in desired:
            desired[doc.kind][doc.full_name] = doc.body
        else:
            reason = "not managed by apply" if doc.kind in NON_APPLY_KINDS else "kind not included in this apply"
            plan["skipped"].append({"kind": doc.kind, "name": doc.name, "where": doc.where, "reason": reason})

    try:
        for kind in kinds:
            if not desired[kind] and not args.prune:
                continue
            current = list_current(ctl, args.domain, kind)
            for name, body in desired[kind].items():
                if name not in current:
                    plan["create"].append({"kind": kind, "name": name})
                    continue
                if kind == "Secret" and body.get("data"):
                    plan["update"].append({"kind": kind, "name": name, "diff": {"changed": ["data (always re-applied)"]}})
                    continue
                diff = spec_diff(body, current[name])
                if any(diff.values()):
                    plan["update"].append({"kind": kind, "name": name, "diff": diff})
                else:
                    plan["unchanged"].append({"kind": kind, "name": name})
            if args.prune:
                doomed = [n for n in current if n not in desired[kind]]
                for name in doomed:
                    entry = {"kind": kind, "name": name}
                    why = INSTALL_BUILTINS.get((kind, name))
                    if why:
                        entry["builtin"] = why
                        plan["dangers"].append(f"deletes install built-in {kind} {name!r}: {why}")
                    plan["delete"].append(entry)
                if current and len(doomed) == len(current):
                    plan["dangers"].append(
                        f"deletes ALL {len(current)} existing {kind} resources (none are described in the given paths)")
        if cluster_config is not None:
            cur = run_ctl(ctl, args.domain, ["get", "clusterconfig"])
            diff = spec_diff(cluster_config, cur)
            plan["clusterConfig"] = diff if any(diff.values()) else "unchanged"
    except CtlError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print_plan(plan)
    return 1 if plan["dangers"] else 0


def print_plan(plan: dict[str, Any]) -> None:
    print(f"Kinds considered: {', '.join(plan['kinds'])}" + ("  (PRUNE ENABLED)" if plan["prune"] else ""))
    for label, key in (("CREATE", "create"), ("UPDATE (spec replaced)", "update"), ("DELETE", "delete")):
        rows = plan[key]
        print(f"\n{label}: {len(rows)}")
        for r in rows:
            print(f"  {r['kind']:<17} {r['name']}" + (f"   <-- {r['builtin']}" if r.get("builtin") else ""))
            diff = r.get("diff") or {}
            for k in ("added", "changed"):
                for f in diff.get(k, [])[:40]:
                    print(f"      {k}: {f}")
            reset = diff.get("reset", [])
            if reset:
                print(f"      in Cluster but not in your file (reset unless the server re-defaults them): {len(reset)} field(s)")
                for f in reset[:40]:
                    print(f"        - {f}")
    print(f"\nUNCHANGED: {len(plan['unchanged'])}")
    if plan["clusterConfig"] is not None:
        cc = plan["clusterConfig"]
        print("\nCLUSTERCONFIG: " + ("unchanged" if cc == "unchanged" else "UPDATE (entire spec replaced)"))
        if cc != "unchanged":
            for k in ("added", "changed", "reset"):
                for f in cc.get(k, [])[:60]:
                    print(f"      {k}: {f}")
    for s in plan["skipped"]:
        print(f"\nSKIPPED {s['kind']} {s['name']} ({s['where']}): {s['reason']}")
    if plan["dangers"]:
        print("\nDANGER:")
        for d in plan["dangers"]:
            print(f"  ! {d}")


if __name__ == "__main__":
    sys.exit(main())
