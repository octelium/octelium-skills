#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["jsonschema>=4"]
# ///
"""Refresh the JSON Schemas bundled with the octelium-management (core/v1) and cordium
(cordium/v1) skills.

Use --from DIR to discover all schemas of one set in a local source checkout (default set:
octelium), or download the currently bundled kinds of every selected set from
OCTELIUM_SCHEMA_BASE_URL and CORDIUM_SCHEMA_BASE_URL (default: published latest schemas).
Exit codes: 0 current/updated, 1 drift in --check, 2 invalid input or unavailable source.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("error: jsonschema is required (uv run scripts/sync_schemas.py, or pip install jsonschema)", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "skills" / "octelium-management" / "assets" / "schemas"
BASE_URL = "https://octelium.com/schemas/octelium/latest"
CORDIUM_DEST = ROOT / "skills" / "cordium" / "assets" / "schemas"
CORDIUM_BASE_URL = "https://octelium.com/schemas/cordium/latest"
DRAFT = "http://json-schema.org/draft-04/schema#"


def read_snapshot(directory: Path, prefix: str = "core.v1") -> dict[str, dict]:
    schema_name = re.compile(rf"^{re.escape(prefix)}\.[A-Za-z][A-Za-z0-9]*\.schema\.json$")
    result: dict[str, dict] = {}
    for path in sorted(directory.glob(f"{prefix}.*.schema.json")):
        if not schema_name.fullmatch(path.name):
            raise ValueError(f"{path}: invalid schema filename")
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(schema, dict) or schema.get("$schema") != DRAFT:
                raise ValueError("expected an Octelium Draft 4 schema object")
            jsonschema.Draft4Validator.check_schema(schema)
            pending = [schema]
            while pending:
                value = pending.pop()
                if isinstance(value, dict):
                    for key in ("definitions", "properties", "patternProperties", "dependencies"):
                        children = value.get(key)
                        if isinstance(children, dict):
                            pending.extend(v for v in children.values() if isinstance(v, dict))
                    for key in ("allOf", "anyOf", "oneOf", "items", "additionalItems", "additionalProperties", "not"):
                        children = value.get(key)
                        if isinstance(children, list):
                            pending.extend(children)
                        elif isinstance(children, dict):
                            pending.append(children)
                    ref = value.get("$ref")
                    if ref is not None:
                        if not ref.startswith("#"):
                            raise ValueError(f"schema reference must be local: {ref!r}")
                        pointer = unquote(ref[1:])
                        if pointer and not pointer.startswith("/"):
                            raise ValueError(f"expected a local JSON Pointer: {ref!r}")
                        target = schema
                        try:
                            for key in pointer[1:].split("/") if pointer else []:
                                key = key.replace("~1", "/").replace("~0", "~")
                                if isinstance(target, list):
                                    if not re.fullmatch(r"0|[1-9][0-9]*", key):
                                        raise ValueError("invalid array index")
                                    target = target[int(key)]
                                else:
                                    target = target[key]
                        except (KeyError, IndexError, TypeError, ValueError):
                            raise ValueError(f"unresolved schema reference: {ref!r}") from None
        except (ValueError, jsonschema.SchemaError) as e:
            raise ValueError(f"{path}: invalid schema: {e}") from e
        result[path.name] = schema
    if not result:
        raise ValueError(f"{directory}: no {prefix} schemas found")
    return result


def fetch_schema(base_url: str, name: str, dest: Path) -> None:
    try:
        proc = subprocess.run(
            ["curl", "-fsSL", "--connect-timeout", "10", "--max-time", "30", "--retry", "2",
             "--retry-max-time", "60", "-A", "octelium-skills-sync (+https://github.com/octelium/octelium-skills)",
             "-o", str(dest), f"{base_url.rstrip('/')}/{name}"],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"{name}: schema source unavailable: {e}") from e
    if proc.returncode:
        raise ValueError(f"{name}: schema source unavailable (curl exit {proc.returncode})")


def replace_snapshot(stage: Path, dest: Path) -> None:
    if dest.is_symlink():
        raise OSError(f"refusing to replace symlink: {dest}")
    backup_dir = Path(tempfile.mkdtemp(dir=dest.parent, prefix=".octelium-schema-backup-"))
    backup = backup_dir / "schemas"
    cleanup = True
    try:
        dest.rename(backup)
        cleanup = False
        try:
            stage.rename(dest)
        except BaseException:
            try:
                backup.rename(dest)
            except OSError as e:
                raise OSError(f"schema update failed; previous snapshot retained at {backup}") from e
            cleanup = True
            raise
        cleanup = True
    finally:
        if cleanup:
            shutil.rmtree(backup_dir)


def sync(source: Path | None, dest: Path, base_url: str, check: bool, prefix: str = "core.v1") -> int:
    current = read_snapshot(dest, prefix)
    with tempfile.TemporaryDirectory(dir=dest.parent, prefix=".octelium-schema-stage-") as directory:
        stage = Path(directory) / "schemas"
        shutil.copytree(dest, stage)
        if source is not None:
            expected = read_snapshot(source, prefix)
            missing = set(current) - set(expected)
            if missing:
                raise ValueError(f"{source}: missing bundled schemas: {', '.join(sorted(missing))}")
            for name in expected:
                shutil.copyfile(source / name, stage / name)
        else:
            for name in current:
                fetch_schema(base_url, name, stage / name)
        expected = read_snapshot(stage, prefix)
        changed = sorted(name for name in expected if current.get(name) != expected[name])
        if check:
            for name in changed:
                print(f"stale: {name}")
            if not changed:
                print("schema snapshot is up to date")
            return 1 if changed else 0
        if changed:
            replace_snapshot(stage, dest)
        print(f"updated {len(expected)} schemas")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="source", type=Path, help="directory containing the complete local schema set")
    ap.add_argument("--set", dest="sets", choices=("octelium", "cordium"), action="append",
                    help="schema set to sync (repeatable; default: both, or octelium with --from)")
    ap.add_argument("--check", action="store_true", help="compare without updating the snapshot")
    args = ap.parse_args()
    sets = {
        "octelium": (DEST, os.environ.get("OCTELIUM_SCHEMA_BASE_URL", BASE_URL), "core.v1"),
        "cordium": (CORDIUM_DEST, os.environ.get("CORDIUM_SCHEMA_BASE_URL", CORDIUM_BASE_URL), "cordium.v1"),
    }
    selected = list(dict.fromkeys(args.sets or (["octelium"] if args.source else list(sets))))
    if args.source is not None and len(selected) > 1:
        print("error: --from takes a single --set", file=sys.stderr)
        return 2
    result = 0
    try:
        for name in selected:
            dest, base_url, prefix = sets[name]
            result = max(result, sync(args.source, dest, base_url, args.check, prefix))
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return result


if __name__ == "__main__":
    sys.exit(main())
