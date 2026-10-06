#!/usr/bin/env python3
"""Generate the bundled CLI reference files from the real Octelium binaries.

The skills tell agents to prefer `<cli> --help` on the installed version. These generated files
are the offline snapshot used when the CLI is not installed yet. Regenerate them for every
Octelium release:

    python3 scripts/generate_cli_reference.py --bin-dir /path/to/release/bin --version v0.43.0

The cordium CLI is versioned separately and is generated only when requested:

    python3 scripts/generate_cli_reference.py --bin-dir /path/to/bin --version v0.15.0 --only cordium

Only the standard library is used. The binaries run with an isolated OCTELIUM_HOME and without
inherited OCTELIUM_* settings. Only version and help commands are executed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from maintenance import replace_files

ROOT = Path(__file__).resolve().parent.parent

# CLI -> skills that bundle its reference.
TARGETS = {
    "octelium": ["octelium-connect"],
    "octeliumctl": ["octelium-management"],
    "octops": ["octelium-kubernetes-install", "octelium-cluster-ops"],
    "cordium": ["cordium"],
}

SEPARATELY_VERSIONED = {"cordium"}

SKIP_SUBCOMMANDS = {"help", "completion"}
GENERATOR_VERSION = "2"


def run_command(binary: str, args: list[str], env: dict[str, str]) -> str:
    label = " ".join([Path(binary).name, *args])
    try:
        proc = subprocess.run([binary, *args], capture_output=True, text=True, env=env,
                              stdin=subprocess.DEVNULL, timeout=60, check=False)
    except subprocess.TimeoutExpired as e:
        raise ValueError(f"{label}: timed out after 60 seconds") from e
    except OSError as e:
        raise ValueError(f"{label}: could not execute: {e}") from e
    if proc.returncode:
        raise ValueError(f"{label}: exited with status {proc.returncode}")
    outputs = []
    for output in (proc.stdout, proc.stderr):
        lines = output.splitlines()
        lines = [ln for ln in lines if not re.match(r"^\d{4}-\d{2}-\d{2}T\S+\s+(DEBUG|INFO|WARN)\b", ln)]
        outputs.append("\n".join(lines).strip("\n"))
    return outputs[0] or outputs[1]


def run_help(binary: str, path: list[str], env: dict[str, str]) -> str:
    text = run_command(binary, [*path, "--help"], env)
    label = " ".join([Path(binary).name, *path])
    if not re.search(r"^Usage:\s*\n\s+" + re.escape(label) + r"(?:\s|$)", text, re.M):
        raise ValueError(f"{label} --help: missing or malformed Usage section")
    return text


def verify_version(binary: str, version: str, env: dict[str, str]) -> None:
    try:
        result = json.loads(run_command(binary, ["version", "-o", "json"], env))
    except json.JSONDecodeError as e:
        raise ValueError(f"{Path(binary).name} version: invalid JSON") from e
    reported = result.get("releaseVersion") if isinstance(result, dict) else None
    if not isinstance(reported, str) or reported.removeprefix("v") != version.removeprefix("v"):
        raise ValueError(f"{Path(binary).name}: requested version {version!r} differs from reported {reported!r}")


def subcommands(text: str) -> list[tuple[str, str]]:
    m = re.search(r"Available Commands:\n(.*?)(?:\n\n|\Z)", text, re.S)
    if not m:
        return []
    ret = []
    for line in m.group(1).splitlines():
        parts = line.strip().split(None, 1)
        if parts and parts[0] not in SKIP_SUBCOMMANDS:
            ret.append((parts[0], parts[1].strip() if len(parts) > 1 else ""))
    return ret


def strip_noise(text: str, is_root: bool) -> str:
    out: list[str] = []
    skipping = False
    for line in text.splitlines():
        if not is_root and line.startswith("Global Flags:"):
            skipping = True
            continue
        if skipping:
            if line.strip() == "" or line.startswith(" "):
                continue
            skipping = False
        if line.startswith("Use \"") and "for more information about a command" in line:
            continue
        if re.match(r"^\s+(help|completion)\s", line):
            continue
        if re.match(r"^\s+-h, --help\s+help for ", line):
            continue
        out.append(line.rstrip())
    # Collapse runs of blank lines.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")


def walk(binary: str, name: str, env: dict[str, str]) -> list[tuple[list[str], str, str]]:
    """Return (path, summary, help) for every command, depth first."""
    result: list[tuple[list[str], str, str]] = []

    def visit(path: list[str], summary: str) -> None:
        if len(path) > 10 or len(result) >= 1000:
            raise ValueError(f"{name}: command traversal exceeded its limit")
        text = run_help(binary, path, env)
        result.append((path, summary, strip_noise(text, is_root=not path)))
        for sub, sub_summary in subcommands(text):
            visit([*path, sub], sub_summary)

    visit([], "")
    return result


def render(name: str, version: str, commands: list[tuple[list[str], str, str]], digest: str) -> str:
    lines = [
        f"# `{name}` command reference",
        "",
        f"<!-- Generated by scripts/generate_cli_reference.py from {name} {version}. Do not edit by hand. -->",
        "",
        f"Snapshot of `{name} --help` for **{version}**. The installed CLI is authoritative: when this",
        f"file and `{name} <command> --help` disagree, trust the installed CLI. Global flags are",
        "shown once, under the root command.",
        "",
        f"Binary SHA-256: `{digest}`. Commands: {len(commands)}. Generator version: {GENERATOR_VERSION}.",
        "",
        "## Index",
        "",
    ]
    for path, summary, _ in commands:
        if not path:
            continue
        label = " ".join([name, *path])
        lines.append(f"- `{label}`" + (f": {summary}" if summary else ""))
    lines.append("")
    for path, _, text in commands:
        label = " ".join([name, *path])
        lines += [f"## `{label}`", "", "```text", text, "```", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bin-dir", help="directory holding the CLI binaries (default: PATH)")
    ap.add_argument("--version", required=True, help="expected binary release version, e.g. v0.43.0")
    ap.add_argument("--only", choices=sorted(TARGETS), action="append",
                    help="generate only these CLIs (default: the Octelium CLIs; cordium only when requested)")
    ap.add_argument("--check", action="store_true", help="report drift without changing files (exit 1)")
    args = ap.parse_args()
    args.version = "v" + args.version.removeprefix("v")

    contents: dict[Path, bytes] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="octelium-help-") as home:
            env = {k: v for k, v in os.environ.items() if not k.startswith("OCTELIUM_")}
            env["OCTELIUM_HOME"] = home
            env["NO_COLOR"] = "1"
            default = [name for name in sorted(TARGETS) if name not in SEPARATELY_VERSIONED]
            for name in dict.fromkeys(args.only or default):
                binary = os.path.join(args.bin_dir, name) if args.bin_dir else shutil.which(name)
                if not binary or not os.access(binary, os.X_OK):
                    raise ValueError(f"{name} binary not found")
                binary = str(Path(binary).absolute())
                verify_version(binary, args.version, env)
                digest = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
                commands = walk(binary, name, env)
                if hashlib.sha256(Path(binary).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"{name}: binary changed during generation")
                content = render(name, args.version, commands, digest).encode("utf-8")
                for skill in TARGETS[name]:
                    dest = ROOT / "skills" / skill / "references" / f"cli-{name}.md"
                    contents[dest] = content
        changed = [p for p, data in contents.items() if not p.exists() or p.read_bytes() != data]
        if args.check:
            for p in changed:
                print(f"stale: {p.relative_to(ROOT)}")
            return 1 if changed else 0
        replace_files({p: contents[p] for p in changed})
        for p in changed:
            print(f"wrote {p.relative_to(ROOT)}")
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
