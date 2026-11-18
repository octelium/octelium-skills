from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = "/docs/cordium/latest"


def document(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}, text
    end = re.search(r"(?m)^---[ \t]*(?:\n|\Z)", text[4:])
    if end is None:
        raise ValueError(f"{path}: malformed frontmatter")
    fields = yaml.safe_load(text[4:4 + end.start()])
    if not isinstance(fields, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping")
    return fields, text[4 + end.end():]


def anchors(content: str) -> set[str]:
    content = re.sub(r"(?ms)^(`{3,}|~{3,})[^\n]*\n.*?^\1[^\n]*$", "", content)
    result: set[str] = set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", content, re.M):
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
        heading = heading.replace("`", "").replace("*", "")
        slug = re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")
        candidate, suffix = slug, 0
        while candidate in result:
            suffix += 1
            candidate = f"{slug}-{suffix}"
        result.add(candidate)
    result.update(re.findall(r'\bid=["\']([^"\']+)["\']', content))
    return result


def routes(docs_dir: Path, base: str = BASE) -> dict[str, set[str]]:
    result = {}
    paths = sorted(docs_dir.rglob("*.mdx")) + sorted(docs_dir.rglob("*.md"))
    if not paths:
        raise ValueError(f"{docs_dir}: no documentation files found")
    for path in paths:
        fields, content = document(path)
        if fields.get("ignore") in (True, "true"):
            continue
        relative = path.relative_to(docs_dir)
        parts = list(relative.parent.parts)
        if path.stem != "index":
            parts.append(str(fields.get("id") or path.stem).strip())
        route = base + ("/" + "/".join(parts) if parts else "")
        if route in result:
            raise ValueError(f"{path}: duplicate route {route}")
        result[route] = anchors(content)
    return result


def validate_links(skill_dir: Path, docs_dir: Path, base: str = BASE) -> tuple[int, list[str]]:
    available = routes(docs_dir, base)
    pattern = re.compile(r"https://octelium\.com" + re.escape(base) + r"(?:/[\w./%#~-]*)?")
    errors = []
    checked = 0
    for path in sorted(skill_dir.rglob("*.md")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for raw in pattern.findall(line):
                url = raw.rstrip(".,")
                target = urlsplit(url)
                route = unquote(target.path).removesuffix(".md").rstrip("/")
                if route == base + "/llms.txt":
                    continue
                checked += 1
                where = f"{path.relative_to(skill_dir)}:{number}"
                if route not in available:
                    errors.append(f"{where}: missing documentation page: {url}")
                elif target.fragment and unquote(target.fragment) not in available[route]:
                    errors.append(f"{where}: missing documentation anchor: {url}")
    if checked == 0:
        errors.append(f"{skill_dir}: no {base.split('/')[2].title()} documentation links found")
    return checked, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check skill links against a local Octelium or Cordium docs source checkout.")
    parser.add_argument("--docs-dir", required=True, type=Path, help="directory containing docs/<set>/latest")
    parser.add_argument("--set", choices=("octelium", "cordium"), default="cordium")
    parser.add_argument("--skill-dir", type=Path)
    args = parser.parse_args()
    skill_dir = args.skill_dir or (ROOT / "skills" / "cordium" if args.set == "cordium" else ROOT / "skills")
    try:
        if not skill_dir.is_dir():
            raise ValueError(f"{skill_dir}: skill directory does not exist")
        checked, errors = validate_links(skill_dir, args.docs_dir, f"/docs/{args.set}/latest")
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"error: {error}")
    print(f"{checked} {args.set.title()} documentation links checked: {len(errors)} error(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
