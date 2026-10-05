#!/usr/bin/env python3
"""Generate compatibility manifests from the portable root plugin.json.

Usage: python3 scripts/generate_plugin_manifests.py [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from maintenance import replace_files

ROOT = Path(__file__).resolve().parent.parent
SHARED_FIELDS = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")


def compatibility_manifests(portable: dict) -> dict[str, dict]:
    if not isinstance(portable, dict):
        raise ValueError("plugin.json must be an object")
    if portable.get("$schema") != "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json":
        raise ValueError("plugin.json: expected the canonical Agent Plugins 1.0.0 schema")
    for field in SHARED_FIELDS:
        if field not in portable:
            raise ValueError(f"plugin.json: missing {field!r}")
    for field in ("name", "version", "description", "homepage", "repository", "license"):
        if not isinstance(portable[field], str) or not portable[field]:
            raise ValueError(f"plugin.json: {field} must be a nonempty string")
    author = portable["author"]
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"]:
        raise ValueError("plugin.json: author.name must be a nonempty string")
    if not isinstance(portable["keywords"], list) or not all(isinstance(k, str) for k in portable["keywords"]):
        raise ValueError("plugin.json: keywords must be an array of strings")
    extensions = portable.get("extensions")
    openai = extensions.get("com.openai") if isinstance(extensions, dict) else None
    interface = openai.get("interface") if isinstance(openai, dict) else None
    if not isinstance(interface, dict) or not isinstance(interface.get("displayName"), str):
        raise ValueError("plugin.json: extensions.com.openai.interface.displayName is required")
    if set(openai) & {*SHARED_FIELDS, "skills", "mcpServers"}:
        raise ValueError("plugin.json: OpenAI settings must not override portable metadata or components")
    shared = {k: portable[k] for k in SHARED_FIELDS}
    return {
        ".codex-plugin/plugin.json": {**shared, "skills": "./skills/", **openai},
        ".claude-plugin/plugin.json": {**shared, "displayName": interface["displayName"]},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="report metadata drift without writing files (exit 1)")
    args = ap.parse_args()
    try:
        portable = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        manifests = compatibility_manifests(portable)
        changed: dict[Path, bytes] = {}
        for path, expected in manifests.items():
            dest = ROOT / path
            if not dest.exists() or json.loads(dest.read_text(encoding="utf-8")) != expected:
                changed[dest] = (json.dumps(expected, indent=2) + "\n").encode("utf-8")
        if args.check:
            for p in changed:
                print(f"stale: {p.relative_to(ROOT)}")
            return 1 if changed else 0
        replace_files(changed)
        for p in changed:
            print(f"wrote {p.relative_to(ROOT)}")
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
