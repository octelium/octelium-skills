#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6", "jsonschema>=4"]
# ///
"""Validate the octelium-skills repository.

Checks:
- every skills/<name>/SKILL.md follows the Agent Skills specification (name, description,
  optional license/compatibility/metadata constraints) and stays within the size budget;
- skills are self-contained: relative links resolve inside the skill directory, and every file in
  references/ is linked from SKILL.md;
- plugin/marketplace manifests are valid JSON and agree on name and version;
- generated CLI references and the bundled JSON Schemas are present;
- core/v1 and cordium/v1 resource examples validate against the bundled JSON Schemas; external
  resources, fragments and Bootstrap examples have explicit classifications and limited parsing
  checks;
- eval cases have a prompt and graders, and skill graders reference existing skills.

Usage: uv run scripts/validate_repo.py   (or python3 with pyyaml and jsonschema installed)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from generate_plugin_manifests import compatibility_manifests

try:
    import yaml
except ImportError:
    print("error: PyYAML is required (uv run scripts/validate_repo.py, or pip install pyyaml jsonschema)", file=sys.stderr)
    sys.exit(2)
try:
    import jsonschema
except ImportError:
    print("error: jsonschema is required (uv run scripts/validate_repo.py, or pip install pyyaml jsonschema)", file=sys.stderr)
    sys.exit(2)

from sync_schemas import read_snapshot

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SCHEMAS = SKILLS / "octelium-management" / "assets" / "schemas"
CORDIUM_SCHEMAS = SKILLS / "cordium" / "assets" / "schemas"
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
MAX_SKILL_LINES = 500
MAX_SKILL_BODY_CHARS = 20000  # ~5000 tokens

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def split_frontmatter(text: str) -> tuple[dict, str] | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    try:
        fm = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return None
    return (fm, text[end + 5:]) if isinstance(fm, dict) else None


def check_skill(skill_dir: Path) -> None:
    md = skill_dir / "SKILL.md"
    if not md.exists():
        err(f"{rel(skill_dir)}: missing SKILL.md")
        return
    text = md.read_text(encoding="utf-8")
    parsed = split_frontmatter(text)
    if parsed is None:
        err(f"{rel(md)}: missing or malformed YAML frontmatter")
        return
    fm, body = parsed
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    for k in fm:
        if k not in allowed:
            err(f"{rel(md)}: unknown frontmatter field {k!r}")
    name = fm.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > 64:
        err(f"{rel(md)}: invalid name {name!r}")
    elif name != skill_dir.name:
        err(f"{rel(md)}: name {name!r} must match directory {skill_dir.name!r}")
    desc = fm.get("description")
    if not isinstance(desc, str) or not (1 <= len(desc) <= 1024):
        err(f"{rel(md)}: description must be 1-1024 characters (got {len(desc) if isinstance(desc, str) else desc!r})")
    comp = fm.get("compatibility")
    if comp is not None and not (isinstance(comp, str) and 1 <= len(comp) <= 500):
        err(f"{rel(md)}: compatibility must be 1-500 characters")
    meta = fm.get("metadata")
    if meta is not None and not (isinstance(meta, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in meta.items())):
        err(f"{rel(md)}: metadata must map strings to strings (quote versions)")
    if "license" not in fm:
        warn(f"{rel(md)}: no license field")
    lines = text.count("\n") + 1
    if lines > MAX_SKILL_LINES:
        err(f"{rel(md)}: {lines} lines exceeds {MAX_SKILL_LINES}")
    if len(body) > MAX_SKILL_BODY_CHARS:
        warn(f"{rel(md)}: body is {len(body)} chars (~{len(body) // 4} tokens); keep it under ~5000 tokens")

    linked: set[Path] = set()
    for f in skill_dir.rglob("*.md"):
        for target in LINK_RE.findall(f.read_text(encoding="utf-8")):
            if re.match(r"^[a-z]+://", target) or target.startswith("#") or target.startswith("mailto:"):
                continue
            path = (f.parent / target.split("#", 1)[0]).resolve()
            try:
                path.relative_to(skill_dir.resolve())
            except ValueError:
                err(f"{rel(f)}: link {target!r} leaves the skill directory (skills must be self-contained)")
                continue
            if not path.exists():
                err(f"{rel(f)}: broken link {target!r}")
            if f == md:
                linked.add(path)
    refs = skill_dir / "references"
    if refs.is_dir():
        for r in sorted(refs.glob("*.md")):
            if r.resolve() not in linked:
                err(f"{rel(r)}: not linked from SKILL.md (agents will never find it)")


def load_object(path: str) -> dict | None:
    try:
        result = json.loads((ROOT / path).read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("expected a JSON object")
        return result
    except (OSError, ValueError) as e:
        err(f"{path}: {e}")
        return None


def check_manifests() -> None:
    portable = load_object("plugin.json")
    schema = load_object("scripts/schemas/agent-plugins-1.0.0.schema.json")
    if portable is not None and schema is not None:
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
            for e in jsonschema.Draft202012Validator(schema).iter_errors(portable):
                err(f"plugin.json: {e.message}")
        except jsonschema.SchemaError as e:
            err(f"portable manifest schema: {e.message}")
    expected = {}
    if portable is not None:
        try:
            expected = compatibility_manifests(portable)
        except ValueError as e:
            err(str(e))
    for path, wanted in expected.items():
        actual = load_object(path)
        if actual is not None and actual != wanted:
            err(f"{path}: differs from plugin.json; run scripts/generate_plugin_manifests.py")
    for mp in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
        manifest = load_object(mp)
        if manifest is None:
            continue
        if not isinstance(manifest.get("name"), str) or not manifest["name"]:
            err(f"{mp}: name must be a nonempty string")
        if mp.startswith(".claude") and not isinstance(manifest.get("owner"), dict):
            err(f"{mp}: owner must be an object")
        entries = manifest.get("plugins")
        if not isinstance(entries, list) or not entries:
            err(f"{mp}: plugins must be a nonempty array")
            continue
        for e in entries:
            if not isinstance(e, dict):
                err(f"{mp}: plugin entry must be an object")
                continue
            if not isinstance(e.get("name"), str) or portable is None or e.get("name") != portable.get("name"):
                err(f"{mp}: plugin name disagrees with plugin.json")
            src = e.get("source")
            path = src if isinstance(src, str) else src.get("path") if isinstance(src, dict) else None
            if not isinstance(path, str) or not path.startswith("./") or ".." in Path(path).parts:
                err(f"{mp}: source path must start with ./ and stay inside the repo")
                continue
            resolved = (ROOT / path).resolve()
            if not resolved.is_relative_to(ROOT.resolve()) or not resolved.is_dir():
                err(f"{mp}: source {path!r} not found inside the repo")
    if not (ROOT / "skills").is_dir():
        err("plugin.json: portable skills/ directory missing")
    skill_versions = set()
    for md in SKILLS.glob("*/SKILL.md"):
        parsed = split_frontmatter(md.read_text(encoding="utf-8"))
        if parsed:
            meta = parsed[0].get("metadata")
            version = meta.get("version") if isinstance(meta, dict) else None
            skill_versions.add(version if isinstance(version, str) else None)
    version = portable.get("version") if portable is not None else None
    if isinstance(version, str) and skill_versions != {version}:
        warn(f"skill metadata versions {sorted(map(str, skill_versions))} differ from plugin version {version}")


def check_generated() -> None:
    expected = {
        "octelium-connect": ["cli-octelium.md"],
        "octelium-management": ["cli-octeliumctl.md"],
        "octelium-kubernetes-install": ["cli-octops.md"],
        "octelium-cluster-ops": ["cli-octops.md"],
        "cordium": ["cli-cordium.md"],
    }
    for skill, files in expected.items():
        for f in files:
            p = SKILLS / skill / "references" / f
            if not p.exists():
                err(f"{rel(p)}: missing; run scripts/generate_cli_reference.py")
            elif "Generated by scripts/generate_cli_reference.py" not in p.read_text(encoding="utf-8"):
                err(f"{rel(p)}: missing the generated-file header")
    if not SCHEMAS.is_dir() or not list(SCHEMAS.glob("core.v1.*.schema.json")):
        err(f"{rel(SCHEMAS)}: schema snapshot missing; run scripts/sync_schemas.sh")
    if not CORDIUM_SCHEMAS.is_dir() or not list(CORDIUM_SCHEMAS.glob("cordium.v1.*.schema.json")):
        err(f"{rel(CORDIUM_SCHEMAS)}: schema snapshot missing; run scripts/sync_schemas.sh --set cordium")
    copies = [SKILLS / s / "references" / "cli-octops.md"
              for s in ("octelium-kubernetes-install", "octelium-cluster-ops")]
    if all(p.exists() for p in copies) and copies[0].read_bytes() != copies[1].read_bytes():
        err("bundled octops references disagree; regenerate both copies together")


PLACEHOLDER = re.compile(r"<([A-Za-z_][A-Za-z0-9_ -]*)>")


def fill_placeholders(text: str) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1).lower()
        if "email" in key:
            return "user@example.com"
        if "url" in key:
            return "https://example.com"
        if "domain" in key:
            return "example.com"
        return "placeholder"
    text = text.replace("<SERVICE>.<NAMESPACE>", "svc.prod")
    return PLACEHOLDER.sub(repl, text)


def check_yaml_examples() -> None:
    try:
        schemas = {name.split(".")[2]: schema for name, schema in read_snapshot(SCHEMAS).items()}
    except (OSError, ValueError) as e:
        err(str(e))
        return
    cordium_schemas: dict[str, dict] = {}
    if CORDIUM_SCHEMAS.is_dir():
        try:
            cordium_schemas = {name.split(".")[2]: schema
                               for name, schema in read_snapshot(CORDIUM_SCHEMAS, "cordium.v1").items()}
        except (OSError, ValueError) as e:
            err(str(e))
    sources: list[tuple[str, str, str]] = []
    for f in sorted(SKILLS.rglob("*.md")):
        if f.name.startswith("cli-"):
            continue
        blocks = re.findall(r"```ya?ml([^\n]*)\n(.*?)```", f.read_text(encoding="utf-8"), re.S)
        for i, (label, block) in enumerate(blocks, start=1):
            sources.append((f"{rel(f)} (yaml block {i})", label.strip() or "octelium", block))
    for f in sorted(SKILLS.glob("*/assets/templates/*.yaml")):
        label = "cordium" if f.parts[-4] == "cordium" else "octelium"
        sources.append((rel(f), label, f.read_text(encoding="utf-8")))
    for f in sorted(SKILLS.glob("*/assets/bootstrap*.yaml")):
        sources.append((rel(f), "bootstrap", f.read_text(encoding="utf-8")))

    checked = 0
    checked_cordium = 0
    for where, label, text in sources:
        if label not in {"octelium", "cordium", "kubernetes", "fragment", "bootstrap"}:
            err(f"{where}: unknown YAML classification {label!r}")
            continue
        try:
            docs = list(yaml.safe_load_all(fill_placeholders(text)))
        except yaml.YAMLError as e:
            err(f"{where}: invalid YAML: {e}")
            continue
        for d in docs:
            if label == "fragment":
                if d is None:
                    err(f"{where}: empty YAML fragment")
                continue
            if not isinstance(d, dict):
                err(f"{where}: expected a YAML mapping")
                continue
            if label == "bootstrap":
                if not isinstance(d.get("spec"), dict):
                    err(f"{where}: expected a Bootstrap spec mapping")
                continue
            kind = d.get("kind")
            api = d.get("apiVersion")
            if label == "kubernetes":
                if not isinstance(api, str) or not api or api == "core/v1" or not isinstance(kind, str) or not kind:
                    err(f"{where}: external Kubernetes example needs apiVersion and kind")
                continue
            if label == "cordium":
                if not isinstance(kind, str) or kind not in cordium_schemas:
                    err(f"{where}: unrecognized Cordium kind {kind!r}")
                    continue
                if api is not None and api != "cordium/v1":
                    err(f"{where}: unsupported Cordium apiVersion {api!r}")
                    continue
                for e in jsonschema.Draft4Validator(cordium_schemas[kind]).iter_errors(d):
                    leaf = jsonschema.exceptions.best_match([e]) if e.context else e
                    path = "/".join(map(str, leaf.absolute_path)) or "(root)"
                    err(f"{where}: {kind}: {path}: {leaf.message}")
                checked_cordium += 1
                continue
            if not isinstance(kind, str) or kind not in schemas:
                err(f"{where}: unrecognized Octelium kind {kind!r}; classify external resources or fragments explicitly")
                continue
            if api is not None and api != "core/v1":
                err(f"{where}: unsupported Octelium apiVersion {api!r}")
                continue
            v = jsonschema.Draft4Validator(schemas[kind])
            for e in v.iter_errors(d):
                leaf = jsonschema.exceptions.best_match([e]) if e.context else e
                path = "/".join(map(str, leaf.absolute_path)) or "(root)"
                err(f"{where}: {kind}: {path}: {leaf.message}")
            checked += 1
    if checked == 0:
        err("no Octelium YAML examples were validated; the extraction is broken")
    else:
        print(f"validated {checked} Octelium resource examples against the bundled schemas")
    if (SKILLS / "cordium").is_dir():
        if checked_cordium == 0:
            err("no Cordium YAML examples were validated; the extraction is broken")
        else:
            print(f"validated {checked_cordium} Cordium resource examples against the bundled schemas")
    print("Bootstrap examples: YAML and spec shape checked; native field and semantic validation not performed")


def check_evals() -> None:
    evals = ROOT / "evals"
    if not evals.is_dir():
        warn("no evals/ directory")
        return
    skill_names = {p.name for p in SKILLS.iterdir() if p.is_dir()}
    cases = [p.parent for p in evals.rglob("prompt.md") if "results" not in p.parts]
    if not cases:
        err("evals/: no cases found")
    for case in cases:
        graders = list((case / "graders").glob("*.md"))
        if not graders:
            err(f"{rel(case)}: no graders")
        parsed = split_frontmatter((case / "prompt.md").read_text(encoding="utf-8"))
        if parsed is None or not parsed[1].strip():
            err(f"{rel(case)}/prompt.md: needs frontmatter and a prompt body")
        else:
            for field, limit in (("runs", None), ("max_turns", 200), ("timeout_seconds", 3600)):
                value = parsed[0].get(field)
                if type(value) is not int or value < 1 or (limit is not None and value > limit):
                    bound = f" from 1 to {limit}" if limit is not None else " greater than zero"
                    err(f"{rel(case)}/prompt.md: {field} must be an integer{bound}")
            tools = parsed[0].get("allowed_tools")
            if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
                err(f"{rel(case)}/prompt.md: allowed_tools must be an array of tool names")
        for g in graders:
            gp = split_frontmatter(g.read_text(encoding="utf-8"))
            if gp is None or "type" not in gp[0]:
                err(f"{rel(g)}: grader needs frontmatter with `type`")
                continue
            for name in re.findall(r"octelium-[a-z-]+|cordium(?:-[a-z-]+)?", str(gp[0].get("input_match", ""))):
                if name not in skill_names:
                    err(f"{rel(g)}: references unknown skill {name!r}")


# Formats that GitHub push protection and other secret scanners flag. Examples and eval prompts
# must use values that don't look like real provider credentials.
SECRET_PATTERNS = re.compile(
    r"sk_(?:live|test)_[0-9A-Za-z]{10,}|rk_live_[0-9A-Za-z]{10,}|AKIA[0-9A-Z]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}"
    r"|xox[abpr]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{35}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
)


def check_secret_like_strings() -> None:
    for f in sorted(ROOT.rglob("*")):
        if not f.is_file() or ".git" in f.parts or f.suffix not in {".md", ".yaml", ".yml", ".json", ".py", ".sh"}:
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            if SECRET_PATTERNS.search(line) and "SECRET_PATTERNS" not in line:
                err(f"{rel(f)}:{n}: looks like a real credential; secret scanners will block the push")


def main() -> int:
    errors.clear()
    warnings.clear()
    try:
        skill_dirs = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    except OSError as e:
        err(f"skills/: {e}")
        skill_dirs = []
    if not skill_dirs:
        err("skills/: no skills found")
    checks = [check_secret_like_strings, *(lambda d=d: check_skill(d) for d in skill_dirs),
              check_manifests, check_generated, check_yaml_examples, check_evals]
    for check in checks:
        try:
            check()
        except (OSError, ValueError) as e:
            err(f"repository check failed: {e}")
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(skill_dirs)} skills checked: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
