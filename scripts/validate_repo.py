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
- every Octelium resource example (```yaml blocks and assets/templates/*.yaml) validates against the
  bundled core/v1 JSON Schemas (placeholders like <NAME> are substituted first);
- eval cases have a prompt and graders, and skill graders reference existing skills.

Usage: uv run scripts/validate_repo.py   (or python3 with pyyaml and jsonschema installed)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("error: PyYAML is required (uv run scripts/validate_repo.py, or pip install pyyaml jsonschema)")
try:
    import jsonschema
except ImportError:
    jsonschema = None

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SCHEMAS = SKILLS / "octelium-management" / "assets" / "schemas"
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
    return yaml.safe_load(text[4:end]) or {}, text[end + 5:]


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


def check_manifests() -> None:
    def load(p: str) -> dict | None:
        path = ROOT / p
        if not path.exists():
            err(f"{p}: missing")
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            err(f"{p}: invalid JSON: {e}")
            return None

    claude = load(".claude-plugin/plugin.json")
    claude_mp = load(".claude-plugin/marketplace.json")
    codex = load(".codex-plugin/plugin.json")
    codex_mp = load(".agents/plugins/marketplace.json")
    if not all([claude, claude_mp, codex, codex_mp]):
        return
    names = {claude.get("name"), codex.get("name"),
             *(p.get("name") for p in claude_mp.get("plugins", [])),
             *(p.get("name") for p in codex_mp.get("plugins", []))}
    if len(names) != 1:
        err(f"plugin names disagree across manifests: {sorted(map(str, names))}")
    if claude.get("version") != codex.get("version"):
        err(f"plugin versions disagree: claude {claude.get('version')} vs codex {codex.get('version')}")
    for key in ("name", "owner", "plugins"):
        if key not in claude_mp:
            err(f".claude-plugin/marketplace.json: missing {key!r}")
    skills_path = codex.get("skills")
    if skills_path and not (ROOT / skills_path).is_dir():
        err(f".codex-plugin/plugin.json: skills path {skills_path!r} not found")
    for mp, entries in ((".claude-plugin/marketplace.json", claude_mp.get("plugins", [])),
                        (".agents/plugins/marketplace.json", codex_mp.get("plugins", []))):
        for e in entries:
            src = e.get("source")
            path = src if isinstance(src, str) else (src or {}).get("path")
            if not path or not path.startswith("./") or ".." in path:
                err(f"{mp}: plugin {e.get('name')!r} source path must start with ./ and stay inside the repo")
            elif not (ROOT / path).is_dir():
                err(f"{mp}: plugin {e.get('name')!r} source {path!r} not found")
    skill_versions = set()
    for md in SKILLS.glob("*/SKILL.md"):
        parsed = split_frontmatter(md.read_text(encoding="utf-8"))
        if parsed:
            skill_versions.add((parsed[0].get("metadata") or {}).get("version"))
    if skill_versions != {claude.get("version")}:
        warn(f"skill metadata versions {sorted(map(str, skill_versions))} differ from plugin version {claude.get('version')}")


def check_generated() -> None:
    expected = {
        "octelium-connect": ["cli-octelium.md"],
        "octelium-management": ["cli-octeliumctl.md"],
        "octelium-kubernetes-install": ["cli-octops.md"],
        "octelium-cluster-ops": ["cli-octops.md"],
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
    if jsonschema is None:
        warn("jsonschema not installed: skipped validating YAML examples")
        return
    schemas: dict[str, dict] = {}
    for p in SCHEMAS.glob("core.v1.*.schema.json"):
        schemas[p.name.split(".")[2]] = json.loads(p.read_text())

    sources: list[tuple[str, str]] = []
    for f in sorted(SKILLS.rglob("*.md")):
        if f.name.startswith("cli-"):
            continue
        for i, block in enumerate(re.findall(r"```yaml\n(.*?)```", f.read_text(encoding="utf-8"), re.S), start=1):
            sources.append((f"{rel(f)} (yaml block {i})", block))
    for f in sorted(SKILLS.glob("*/assets/templates/*.yaml")):
        sources.append((rel(f), f.read_text(encoding="utf-8")))

    checked = 0
    for where, text in sources:
        if "kind:" not in text:
            continue
        try:
            docs = [d for d in yaml.safe_load_all(fill_placeholders(text)) if d]
        except yaml.YAMLError as e:
            err(f"{where}: invalid YAML: {e}")
            continue
        for d in docs:
            if not isinstance(d, dict):
                continue
            kind = d.get("kind")
            api = d.get("apiVersion")
            if kind not in schemas or (api and api != "core/v1"):
                continue  # Kubernetes, cert-manager, ... examples
            v = jsonschema.Draft4Validator(schemas[kind])
            for e in v.iter_errors(d):
                leaf = jsonschema.exceptions.best_match([e]) if e.context else e
                path = "/".join(map(str, leaf.absolute_path)) or "(root)"
                err(f"{where}: {kind} {d.get('metadata', {}).get('name')!r}: {path}: {leaf.message}")
            checked += 1
    if checked == 0:
        err("no Octelium YAML examples were validated; the extraction is broken")
    else:
        print(f"validated {checked} Octelium resource examples against the bundled schemas")


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
        for g in graders:
            gp = split_frontmatter(g.read_text(encoding="utf-8"))
            if gp is None or "type" not in gp[0]:
                err(f"{rel(g)}: grader needs frontmatter with `type`")
                continue
            for name in re.findall(r"octelium-[a-z-]+", str(gp[0].get("input_match", ""))):
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
    check_secret_like_strings()
    skill_dirs = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    if not skill_dirs:
        err("skills/: no skills found")
    for d in skill_dirs:
        check_skill(d)
    check_manifests()
    check_generated()
    check_yaml_examples()
    check_evals()
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"{len(skill_dirs)} skills checked: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
