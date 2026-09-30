#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6", "jsonschema>=4"]
# ///
"""Validate Octelium resource YAML against the published JSON Schemas, offline from the Cluster.

`octeliumctl apply` has no dry-run and only *warns* about unknown fields (it silently drops
them). Run this before applying:

    uv run scripts/validate_resources.py ./octelium/            # or: python3 scripts/validate_resources.py ...
    uv run scripts/validate_resources.py svc.yaml --offline      # bundled schema snapshot only
    cat svc.yaml | uv run scripts/validate_resources.py -

Schema source, in order: --schema-dir; the latest published schemas at --schema-base-url
(unless --offline); the snapshot bundled in ../assets/schemas. The script reads files only; it
never contacts the Cluster.

Exit status: 0 no errors, 1 validation errors, 2 usage/environment problems.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import NON_APPLY_KINDS, Doc, load_documents  # noqa: E402

try:
    import jsonschema
except ImportError:
    sys.stderr.write(
        "error: the jsonschema package is required. Run with `uv run scripts/validate_resources.py ...`\n"
        "or install it with `python3 -m pip install pyyaml jsonschema`.\n"
    )
    sys.exit(2)

BUNDLED = Path(__file__).resolve().parent.parent / "assets" / "schemas"
DEFAULT_BASE_URL = "https://octelium.com/schemas/octelium/latest"
USER_AGENT = "octelium-skills/0.1 (+https://github.com/octelium/octelium-skills)"


class SchemaSource:
    def __init__(self, schema_dir: str | None, base_url: str, offline: bool) -> None:
        self.schema_dir = Path(schema_dir) if schema_dir else None
        self.base_url = base_url.rstrip("/")
        self.offline = offline
        self.cache: dict[str, tuple[dict[str, Any], str] | None] = {}
        self.online_failed = False

    def get(self, kind: str) -> tuple[dict[str, Any], str] | None:
        if kind not in self.cache:
            self.cache[kind] = self._load(kind)
        return self.cache[kind]

    def _load(self, kind: str) -> tuple[dict[str, Any], str] | None:
        fname = f"core.v1.{kind}.schema.json"
        if self.schema_dir:
            p = self.schema_dir / fname
            return (json.loads(p.read_text()), str(p)) if p.exists() else None
        if not self.offline and not self.online_failed:
            url = f"{self.base_url}/{fname}"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode("utf-8")), url
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    return None
                self.online_failed = True
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                self.online_failed = True
        p = BUNDLED / fname
        return (json.loads(p.read_text()), f"bundled snapshot {p.name}") if p.exists() else None


def fmt_path(path: Any) -> str:
    parts = [str(p) for p in path]
    return "/".join(parts) if parts else "(root)"


def best_errors(validator: Any, body: dict[str, Any]) -> list[str]:
    msgs = []
    for err in sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path)):
        # oneOf/anyOf failures are noisy; report the most relevant sub-error instead.
        leaf = jsonschema.exceptions.best_match([err]) if err.context else err
        msgs.append(f"{fmt_path(leaf.absolute_path)}: {leaf.message}")
    return sorted(set(msgs))


NAME_SEGMENT = re.compile(r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$")


def name_errors(doc: Doc) -> list[str]:
    """Mirror the API server's name validation (cluster/common/apivalidation)."""
    if doc.kind == "ClusterConfig":
        return []
    parts = doc.name.split(".")
    max_parts = 2 if doc.kind == "Service" else 1
    errs = []
    if len(parts) > max_parts:
        errs.append(f"metadata.name {doc.name!r}: " + (
            "a Service name is `<name>` or `<name>.<namespace>`" if doc.kind == "Service"
            else "only Services may have a `.namespace` suffix"))
    bad = [p for p in parts if not NAME_SEGMENT.match(p) or "--" in p]
    if bad:
        errs.append(f"metadata.name {doc.name!r}: each part must be 2-40 chars of [a-z0-9-], start with a "
                    "letter, end with a letter or digit, and have no consecutive hyphens")
    if len(doc.name) > 128:
        errs.append("metadata.name is longer than 128 characters")
    return errs


def lint(doc: Doc) -> list[str]:
    """Advisory warnings for risky or surprising content."""
    w: list[str] = []
    b, spec = doc.body, doc.body.get("spec") or {}
    if doc.kind in NON_APPLY_KINDS:
        w.append(f"`octeliumctl apply` does not manage {doc.kind} resources; it will skip this document")
    api = b.get("apiVersion")
    if api not in (None, "core/v1"):
        w.append(f"apiVersion is {api!r}; Core resources use 'core/v1' (or omit it)")
    if doc.kind == "Secret" and b.get("data"):
        w.append("contains plaintext Secret data: keep it out of git; apply needs --include-secret")
    if doc.kind == "ClusterConfig":
        w.append("apply replaces the ENTIRE ClusterConfig spec: start from `octeliumctl get cc -o yaml`")
    if doc.kind == "Service":
        if spec.get("isAnonymous"):
            w.append("isAnonymous: anyone on the internet can reach this Service without authentication")
        elif spec.get("isPublic"):
            w.append("isPublic: reachable from the internet through the Ingress (authentication still required)")
    for holder in ("authorization",):
        auth = spec.get(holder) or {}
        if "allow-all" in (auth.get("policies") or []):
            w.append("attaches the `allow-all` Policy: full access to everything, including the Octelium API")
        for ip in auth.get("inlinePolicies") or []:
            for rule in ((ip or {}).get("spec") or {}).get("rules") or []:
                if (rule or {}).get("effect") == "ALLOW" and ((rule or {}).get("condition") or {}).get("matchAny"):
                    w.append("inline Policy with an unconditional ALLOW (matchAny)")
    if doc.kind == "Policy":
        for rule in spec.get("rules") or []:
            if (rule or {}).get("effect") == "ALLOW" and ((rule or {}).get("condition") or {}).get("matchAny"):
                w.append("rule ALLOWs unconditionally (matchAny): everything it is attached to becomes fully accessible")
        if spec.get("isDisabled"):
            w.append("isDisabled: this Policy's rules are not evaluated")
    if doc.kind == "User" and spec.get("isDisabled"):
        w.append("isDisabled: the User loses access immediately")
    return w


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="YAML files, directories (recursive) or - for stdin")
    ap.add_argument("--schema-dir", help="directory with core.v1.<Kind>.schema.json files (e.g. pinned to a release)")
    ap.add_argument("--schema-base-url", default=DEFAULT_BASE_URL, help=f"default: {DEFAULT_BASE_URL}")
    ap.add_argument("--offline", action="store_true", help="use the bundled schema snapshot only")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    docs = load_documents(args.paths)
    source = SchemaSource(args.schema_dir, args.schema_base_url, args.offline)
    results = []
    seen: dict[tuple[str, str], str] = {}
    n_err = 0

    for doc in docs:
        errors: list[str] = []
        if not doc.kind:
            errors.append("missing `kind`")
        if not doc.name:
            errors.append("missing `metadata.name`")
        if doc.name:
            errors += name_errors(doc)
        key = (doc.kind, doc.full_name)
        if doc.kind and doc.name:
            if key in seen:
                errors.append(f"duplicate {doc.kind} {doc.full_name!r} (also in {seen[key]})")
            seen[key] = doc.where
        used = None
        if doc.kind:
            loaded = source.get(doc.kind)
            if loaded is None:
                errors.append(f"unknown kind {doc.kind!r} (no published core/v1 schema)")
            else:
                schema, used = loaded
                errors += best_errors(jsonschema.Draft4Validator(schema), doc.body)
        warnings = lint(doc) if doc.kind else []
        n_err += len(errors)
        results.append({"where": doc.where, "kind": doc.kind, "name": doc.name,
                        "schema": used, "errors": errors, "warnings": warnings})

    if args.json:
        print(json.dumps({"documents": results, "errorCount": n_err,
                          "onlineSchemasUnavailable": source.online_failed}, indent=2))
    else:
        if source.online_failed:
            print("note: published schemas unreachable; fell back to the bundled snapshot\n")
        for r in results:
            status = "FAIL" if r["errors"] else ("WARN" if r["warnings"] else "ok")
            print(f"[{status}] {r['kind'] or '?'} {r['name'] or '?'}  ({r['where']})")
            for e in r["errors"]:
                print(f"    error: {e}")
            for w in r["warnings"]:
                print(f"    warning: {w}")
        used = sorted({r["schema"] for r in results if r["schema"]})
        origins = sorted({u.rsplit("/", 1)[0] if "://" in u else ("bundled snapshot" if u.startswith("bundled") else str(Path(u).parent)) for u in used})
        print(f"\n{len(results)} document(s), {n_err} error(s); schemas from: {', '.join(origins) or 'none'}")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
