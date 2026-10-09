#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6", "jsonschema>=4"]
# ///
"""Validate Cordium YAML (Workspace and Template specs, the Cordium ClusterConfig and the other
cordium/v1 kinds) against the published JSON Schemas and the API server's own checks.

`cordium run/create workspace --file` and `cordium create template -f` drop unknown fields
without a message, and the API rejects some values only when the Workspace is created. Run
this before using a file:

    uv run scripts/validate_resources.py workspace.yaml template.yaml   # or: python3 scripts/...
    uv run scripts/validate_resources.py --kind Workspace .cordium.yaml  # documents without kind
    cat cluster-config.yaml | uv run scripts/validate_resources.py -

Schema source, in order: --schema-dir; the latest published schemas at --schema-base-url
(unless --offline); the snapshot bundled in ../assets/schemas. The script reads files only; it
never contacts the Cluster.

Exit status: 0 no errors, 1 validation errors, 2 usage/environment problems.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import posixpath
import re
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator

try:
    import yaml
except ImportError:
    sys.stderr.write(
        "error: PyYAML is required. Run with `uv run scripts/validate_resources.py ...`\n"
        "or install it with `python3 -m pip install pyyaml jsonschema`.\n"
    )
    sys.exit(2)
try:
    import jsonschema
except ImportError:
    sys.stderr.write(
        "error: the jsonschema package is required. Run with `uv run scripts/validate_resources.py ...`\n"
        "or install it with `python3 -m pip install pyyaml jsonschema`.\n"
    )
    sys.exit(2)

BUNDLED = Path(__file__).resolve().parent.parent / "assets" / "schemas"
DEFAULT_BASE_URL = "https://octelium.com/schemas/cordium/latest"
USER_AGENT = "octelium-skills/0.1 (+https://github.com/octelium/octelium-skills)"

KINDS = {"Workspace", "Template", "ClusterConfig", "Space", "Membership", "Secret", "GitProvider",
         "UserSecret", "UserConfig", "Volume", "WorkspaceSnapshot", "Region"}
CREATED_BY = {
    "Space": "`cordium create space` and the web console",
    "Membership": "the web console",
    "Secret": "`cordium create secret`",
    "GitProvider": "`cordium create gitprovider`",
    "UserSecret": "`cordium create usersecret`",
    "UserConfig": "the web console",
    "Volume": "`cordium create volume`",
    "WorkspaceSnapshot": "`cordium create snapshot`",
    "Region": "the Cluster (read only)",
}

NAME_SEGMENT = re.compile(r"^[a-z][a-z0-9-]{0,38}[a-z0-9]$")
GIT_REF = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/+-]{0,254}$")
CAPABILITY = re.compile(r"^(ALL|[A-Z][A-Z0-9_]{0,29})$")
VAR_EXACT = re.compile(r"\$\{\{ vars\.([^\s{}]+) \}\}|\$\{\{vars\.([^\s{}]+)\}\}")
VAR_ANY = re.compile(r"\$\{\{.*?\}\}")
BROAD_CAPABILITIES = {"ALL", "SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "SYS_MODULE", "DAC_READ_SEARCH"}
RESERVED_MOUNT_PATHS = {"/", "/bin", "/boot", "/etc", "/lib", "/lib32", "/lib64", "/root", "/sbin",
                        "/tmp", "/usr", "/var", "/var/tmp", "/workspace"}
RESERVED_MOUNT_TREES = ["/dev", "/octelium", "/proc", "/run", "/sys", "/var/lib/containers",
                        "/var/lib/docker", "/var/run"]
SUBSTITUTED = [
    re.compile(p) for p in (
        r"image/registry/url", r"image/dockerfile/url", r"image/git/(url|checkout|dockerfile|context)",
        r"repository/(url|cloneOptions/(branch|checkout))",
        r"additionalRepositories/\d+/repository/(url|cloneOptions/(branch|checkout))",
        r"runtime/envVars/\d+/value", r"runtime/tasks/\d+/(run|workingDir|envVars/\d+/value)",
    )
]


class InputError(ValueError):
    pass


class Loader(yaml.SafeLoader):
    pass


Loader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in resolvers
          if tag not in ("tag:yaml.org,2002:bool", "tag:yaml.org,2002:timestamp")]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def construct_mapping(loader: Loader, node: Any, deep: bool = False) -> dict[str, Any]:
    seen = set()
    for key_node, _ in node.value:
        key = "<<" if key_node.tag == "tag:yaml.org,2002:merge" else loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, "mapping keys must be strings", key_node.start_mark)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping", node.start_mark, f"duplicate key {key!r}", key_node.start_mark)
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


Loader.add_constructor("tag:yaml.org,2002:map", construct_mapping)


def yaml_files(path: str) -> list[str]:
    mode = os.stat(path).st_mode
    if stat.S_ISDIR(mode):
        found = []
        for root, _dirs, files in os.walk(path):
            for name in files:
                candidate = os.path.join(root, name)
                if name.lower().endswith((".yaml", ".yml")) and stat.S_ISREG(os.lstat(candidate).st_mode):
                    found.append(candidate)
        return sorted(found)
    if stat.S_ISREG(mode):
        return [path]
    raise OSError(f"the path {path} is neither a regular file nor a directory")


def load_documents(paths: list[str]) -> list[tuple[str, dict[str, Any]]]:
    docs = []
    for arg in paths:
        for src in (["-"] if arg == "-" else yaml_files(arg)):
            if src == "-":
                text = sys.stdin.read()
            else:
                with open(src, encoding="utf-8") as stream:
                    text = stream.read()
            try:
                bodies = list(yaml.load_all(text, Loader=Loader))
            except yaml.YAMLError as err:
                raise InputError(f"{src}: invalid YAML: {err}") from err
            numbered = [(idx, body) for idx, body in enumerate(bodies, start=1) if body is not None]
            for idx, body in numbered:
                where = src if len(bodies) == 1 else f"{src} (document {idx})"
                if not isinstance(body, dict):
                    raise InputError(f"{where}: expected a mapping, got {type(body).__name__}")
                try:
                    json.dumps(body, allow_nan=False)
                except (TypeError, ValueError, RecursionError) as err:
                    raise InputError(f"{where}: document cannot be represented as JSON: {err}") from err
                docs.append((where, body))
    if not docs:
        raise InputError(f"could not find any YAML documents in: {', '.join(paths)}")
    return docs


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
        fname = f"cordium.v1.{kind}.schema.json"
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


def schema_errors(schema: dict[str, Any], body: dict[str, Any]) -> list[str]:
    jsonschema.Draft4Validator.check_schema(schema)
    msgs = []
    for err in jsonschema.Draft4Validator(schema).iter_errors(body):
        leaf = jsonschema.exceptions.best_match([err]) if err.context else err
        msgs.append(f"{'/'.join(map(str, leaf.absolute_path)) or '(root)'}: {leaf.message}")
    return sorted(set(msgs))


def mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def is_full_space_child(name: str) -> bool:
    return len(name.split(".")) == 3


def strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, f"{path}/{key}" if path else key)
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from strings(child, f"{path}/{idx}" if path else str(idx))


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.prefix = ""

    def error(self, msg: str) -> None:
        self.errors.append(self.prefix + msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(self.prefix + msg)


def check_env_var(r: Report, env: Any, path: str, secret_field: str) -> None:
    env = mapping(env)
    key = text(env.get("key"))
    if not key:
        r.error(f"{path}: key must be set")
    elif len(key) > 64 or not key.isascii():
        r.error(f"{path}: key must be ASCII and at most 64 characters")
    if "value" in env:
        value = text(env.get("value"))
        if not value:
            r.error(f"{path}: empty value for {key or 'the variable'}")
        elif len(value) > 1024:
            r.error(f"{path}: value is longer than 1024 characters")
    elif secret_field in env:
        ref = text(env.get(secret_field))
        if not ref:
            r.error(f"{path}: empty {secret_field}")
        elif secret_field == "fromSecret" and not is_full_space_child(ref):
            r.warn(f"{path}: fromSecret {ref!r} is not a full name: the API matches `<name>.<space>.<owner>`")
        elif secret_field == "fromUserSecret" and len(ref.split(".")) != 2:
            r.warn(f"{path}: fromUserSecret {ref!r} is not a full name: the API matches `<name>.<user>`")
    else:
        r.error(f"{path}: no value or {secret_field} for {key or 'the variable'}")


def check_tasks(r: Report, tasks: Any, path: str) -> None:
    tasks = sequence(tasks)
    if len(tasks) > 128:
        r.error(f"{path}: more than 128 tasks")
    for idx, task in enumerate(tasks):
        task, where = mapping(task), f"{path}/{idx}"
        run = text(task.get("run"))
        if not run:
            r.error(f"{where}: run must be set")
        elif len(run) > 5000:
            r.error(f"{where}: run is longer than 5000 characters")
        if task.get("type") in (None, "UNKNOWN"):
            r.error(f"{where}: type must be ON_CREATE, POST_START or PRE_STOP")
        if len(text(task.get("workingDir"))) > 256:
            r.error(f"{where}: workingDir is longer than 256 characters")
        envs = sequence(task.get("envVars"))
        if len(envs) > 128:
            r.error(f"{where}/envVars: more than 128 variables")
        for jdx, env in enumerate(envs):
            env = mapping(env)
            key, value = text(env.get("key")), text(env.get("value"))
            if not key or len(key) > 64 or not key.isascii():
                r.error(f"{where}/envVars/{jdx}/key: must be set, ASCII and at most 64 characters")
            if not value or len(value) > 1024:
                r.error(f"{where}/envVars/{jdx}/value: must be 1 to 1024 characters")


def check_git_ref(r: Report, value: Any, path: str) -> None:
    ref = text(value)
    if not ref:
        return
    if "${{" in ref:
        r.error(f"{path}: the API validates it before variable substitution and rejects {ref!r}; "
                "use --branch or a task that checks the ref out")
    elif not GIT_REF.match(ref) or ".." in ref or ref.endswith((".lock", "/")):
        r.error(f"{path}: invalid git ref {ref!r}")


def check_repository(r: Report, repo: Any, path: str, url_required: bool) -> None:
    repo = mapping(repo)
    url = text(repo.get("url"))
    if not url:
        if url_required:
            r.error(f"{path}/url: repository URL is empty")
    elif url.startswith("${{") or "${{ " in url:
        r.error(f"{path}/url: the API validates the URL before variable substitution; "
                "use a full https URL, with references written as ${{vars.NAME}} inside it")
    elif not url.startswith("https://"):
        r.error(f"{path}/url: only https:// repository URLs are supported")
    clone = mapping(repo.get("cloneOptions"))
    check_git_ref(r, clone.get("branch"), f"{path}/cloneOptions/branch")
    check_git_ref(r, clone.get("checkout"), f"{path}/cloneOptions/checkout")
    if clone.get("depth") and not clone.get("disableLazyUnshallow"):
        r.warn(f"{path}/cloneOptions/depth: only effective with disableLazyUnshallow: true")
    http = mapping(mapping(repo.get("authentication")).get("http"))
    if repo.get("authentication") is not None:
        if not text(http.get("username")):
            r.error(f"{path}/authentication/http/username must be set")
        secret = text(mapping(http.get("password")).get("fromSecret"))
        if not secret:
            r.error(f"{path}/authentication/http/password/fromSecret must be set")
        elif not is_full_space_child(secret):
            r.warn(f"{path}/authentication/http/password/fromSecret {secret!r} is not a full "
                   "`<name>.<space>.<owner>` name")


def check_mount_path(r: Report, value: Any, path: str) -> None:
    mount = text(value)
    if not mount:
        r.error(f"{path}: mountPath must be set")
    elif len(mount) > 256 or not mount.startswith("/"):
        r.error(f"{path}: mountPath must be absolute and at most 256 characters")
    elif posixpath.normpath(mount) != mount or "\\" in mount:
        r.error(f"{path}: mountPath must be a clean canonical path ({posixpath.normpath(mount)})")
    elif mount in RESERVED_MOUNT_PATHS or any(mount == t or mount.startswith(t + "/") for t in RESERVED_MOUNT_TREES):
        r.error(f"{path}: mountPath {mount} is reserved by the Cluster")


def check_runtime(r: Report, runtime: Any, path: str) -> None:
    runtime = mapping(runtime)
    envs = sequence(runtime.get("envVars"))
    if len(envs) > 128:
        r.error(f"{path}/envVars: more than 128 variables")
    for idx, env in enumerate(envs):
        check_env_var(r, env, f"{path}/envVars/{idx}", "fromSecret")
    check_tasks(r, runtime.get("tasks"), f"{path}/tasks")
    for field in ("cmd", "entrypoint"):
        if len(text(runtime.get(field))) > 1024:
            r.error(f"{path}/{field}: longer than 1024 characters")
    caps = mapping(runtime.get("capabilities"))
    for field in ("add", "drop"):
        values = sequence(caps.get(field))
        if len(values) > 100:
            r.error(f"{path}/capabilities/{field}: more than 100 capabilities")
        for cap in values:
            if not CAPABILITY.match(text(cap)):
                r.error(f"{path}/capabilities/{field}: invalid capability {cap!r}")
            elif field == "add" and cap in BROAD_CAPABILITIES:
                r.warn(f"{path}/capabilities/add: {cap} widens what code in the Workspace can do")
    features = sequence(mapping(runtime.get("devcontainers")).get("features"))
    if len(features) > 100:
        r.error(f"{path}/devcontainers/features: more than 100 features")
    for idx, feature in enumerate(features):
        feature, where = mapping(feature), f"{path}/devcontainers/features/{idx}"
        reference = text(feature.get("reference"))
        if not reference or len(reference) > 256 or not reference.isascii():
            r.error(f"{where}/reference: must be set, ASCII and at most 256 characters")
        options = sequence(feature.get("options"))
        if len(options) > 32:
            r.error(f"{where}/options: more than 32 options")
        for jdx, option in enumerate(options):
            for field in ("key", "value"):
                value = text(mapping(option).get(field))
                if not value or len(value) > 256 or not value.isascii():
                    r.error(f"{where}/options/{jdx}/{field}: must be set, ASCII and at most 256 characters")
    octelium = mapping(runtime.get("octelium"))
    services = sequence(octelium.get("serveServices"))
    if len(services) > 128:
        r.error(f"{path}/octelium/serveServices: more than 128 Services")
    for svc in services:
        parts = text(svc).split(".")
        if len(parts) > 2 or not all(NAME_SEGMENT.match(p) and "--" not in p for p in parts):
            r.error(f"{path}/octelium/serveServices: invalid Service name {svc!r} (`<svc>` or `<svc>.<namespace>`)")
    if octelium.get("serveAll") or services:
        r.warn(f"{path}/octelium: the Workspace serves its owner's Octelium Services to other Users")
    egress = mapping(mapping(runtime.get("network")).get("egress"))
    rules = sequence(egress.get("rules"))
    if len(rules) > 64:
        r.error(f"{path}/network/egress/rules: more than 64 rules")
    for idx, rule in enumerate(rules):
        rule, where = mapping(rule), f"{path}/network/egress/rules/{idx}"
        if rule.get("action") not in ("ALLOW", "DENY"):
            r.error(f"{where}/action: must be ALLOW or DENY")
        cidrs, ports = sequence(rule.get("cidrs")), sequence(rule.get("ports"))
        if not cidrs or len(cidrs) > 64:
            r.error(f"{where}/cidrs: between 1 and 64 CIDRs are required")
        for cidr in cidrs:
            try:
                ipaddress.ip_network(text(cidr), strict=True)
            except ValueError:
                r.error(f"{where}/cidrs: {cidr!r} is not a canonical CIDR (e.g. 10.0.0.0/8)")
        if len(ports) > 64:
            r.error(f"{where}/ports: more than 64 ports")
        for port in ports:
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
                r.error(f"{where}/ports: invalid port {port!r}")
    if egress.get("defaultAction") == "DENY":
        r.warn(f"{path}/network/egress: defaultAction DENY requires ALLOW rules for DNS and the "
               "Cluster's public Gateway addresses for octelium connect; test connectivity")
    if mapping(runtime.get("timeout")).get("mode") == "DISABLED":
        r.warn(f"{path}/timeout: DISABLED takes effect only with ClusterConfig "
               "workspace.timeout.allowNoTimeout")
    mounts = sequence(runtime.get("volumeMounts"))
    if len(mounts) > 16:
        r.error(f"{path}/volumeMounts: more than 16 mounts")
    seen_paths: list[str] = []
    seen_volumes: list[str] = []
    for idx, mount in enumerate(mounts):
        mount, where = mapping(mount), f"{path}/volumeMounts/{idx}"
        ref = mapping(mount.get("volumeRef"))
        volume = text(ref.get("name")) or text(ref.get("uid"))
        if not volume:
            r.error(f"{where}/volumeRef: name must be set")
        elif volume in seen_volumes:
            r.error(f"{where}: the Volume {volume} is mounted more than once")
        seen_volumes.append(volume)
        check_mount_path(r, mount.get("mountPath"), f"{where}/mountPath")
        mount_path = text(mount.get("mountPath"))
        for other in seen_paths:
            if mount_path and (other == mount_path or other.startswith(mount_path + "/") or mount_path.startswith(other + "/")):
                r.error(f"{where}/mountPath: {mount_path} overlaps {other}")
        seen_paths.append(mount_path)


def check_image(r: Report, image: Any) -> None:
    image = mapping(image)
    if "dockerfile" in image:
        dockerfile = mapping(image.get("dockerfile"))
        if "inline" in dockerfile:
            inline = text(dockerfile.get("inline"))
            if not inline:
                r.error("image/dockerfile/inline: empty Dockerfile")
            elif len(inline) > 5000:
                r.error("image/dockerfile/inline: longer than 5000 characters; use a URL or a repository")
    if "registry" in image:
        registry = mapping(image.get("registry"))
        if not text(registry.get("url")):
            r.error("image/registry/url: image URL is empty")
        if registry.get("authentication") is not None:
            auth = mapping(registry.get("authentication"))
            if not text(auth.get("username")):
                r.error("image/registry/authentication/username must be set")
            secret = text(mapping(auth.get("password")).get("fromSecret"))
            if not secret:
                r.error("image/registry/authentication/password/fromSecret must be set")
            elif not is_full_space_child(secret):
                r.warn(f"image/registry/authentication/password/fromSecret {secret!r} is not a full "
                       "`<name>.<space>.<owner>` name")
    if "git" in image:
        git = mapping(image.get("git"))
        if not text(git.get("url")):
            r.error("image/git/url must be set")
        check_git_ref(r, git.get("checkout"), "image/git/checkout")


def check_variables(r: Report, kind: str, spec: dict[str, Any]) -> None:
    defined = {text(mapping(v).get("name")) for v in sequence(spec.get("vars"))}
    for idx, var in enumerate(sequence(spec.get("vars"))):
        if not text(mapping(var).get("name")):
            r.error(f"vars/{idx}/name must be set")
    undefined = set()
    for path, value in strings(spec):
        if "${{" not in value or path.startswith("vars/"):
            continue
        if not any(p.fullmatch(path) for p in SUBSTITUTED):
            r.warn(f"{path}: variables are not substituted here; the reference stays literal")
            continue
        exact = [m.group(0) for m in VAR_EXACT.finditer(value)]
        for ref in VAR_ANY.findall(value):
            if ref not in exact:
                r.warn(f"{path}: {ref} is not a `${{{{ vars.NAME }}}}` reference and is removed")
        for match in VAR_EXACT.finditer(value):
            name = match.group(1) or match.group(2)
            if name not in defined:
                undefined.add(name)
    source = "the Workspace or `--var`" if kind == "Template" else "the Template or `--var`"
    for name in sorted(undefined):
        r.warn(f"vars: {name} is not defined here; it must come from {source}, otherwise references become empty")


def check_spec(r: Report, kind: str, spec: dict[str, Any]) -> None:
    check_image(r, spec.get("image"))
    if spec.get("repository") is not None:
        check_repository(r, spec.get("repository"), "repository", url_required=False)
    repos = sequence(spec.get("additionalRepositories"))
    if len(repos) > 32:
        r.error("additionalRepositories: more than 32 repositories")
    names: list[str] = []
    for idx, repo in enumerate(repos):
        repo, where = mapping(repo), f"additionalRepositories/{idx}"
        name = text(repo.get("name"))
        if not NAME_SEGMENT.match(name) or "--" in name:
            r.error(f"{where}/name: {name!r} must be 2-40 characters of [a-z0-9-] starting with a letter")
        elif name in names:
            r.error(f"{where}/name: duplicate name {name!r}")
        names.append(name)
        if repo.get("clonePath"):
            r.warn(f"{where}/clonePath: ignored; the repository is cloned to /workspace/additional-repos/{name}")
        if repo.get("repository") is None:
            r.error(f"{where}/repository must be set")
        else:
            check_repository(r, repo.get("repository"), f"{where}/repository", url_required=True)
    check_runtime(r, spec.get("runtime"), "runtime")
    apps = sequence(spec.get("applications"))
    if len(apps) > 128:
        r.error("applications: more than 128 applications")
    app_names: list[str] = []
    defaults = 0
    for idx, app in enumerate(apps):
        app, where = mapping(app), f"applications/{idx}"
        name = text(app.get("name"))
        if not NAME_SEGMENT.match(name) or "--" in name:
            r.error(f"{where}/name: {name!r} must be 2-40 characters of [a-z0-9-] starting with a letter")
        elif name in app_names:
            r.error(f"{where}/name: duplicate name {name!r}")
        app_names.append(name)
        port = app.get("port")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            r.error(f"{where}/port: must be between 1 and 65535")
        if len(text(app.get("displayName"))) > 128:
            r.error(f"{where}/displayName: longer than 128 characters")
        defaults += bool(app.get("isDefault"))
    if defaults > 1:
        r.error("applications: at most one application can be isDefault")
    limit = mapping(spec.get("limit"))
    for field, unit, maximum in (("cpu", "millicores", 1_000_000), ("memory", "megabytes", 10_000_000),
                                 ("storage", "megabytes", 10_000_000)):
        value = mapping(limit.get(field)).get(unit)
        if isinstance(value, int) and value > maximum:
            r.error(f"limit/{field}/{unit}: larger than {maximum}")
    check_variables(r, kind, spec)
    if kind == "Template":
        provider = text(spec.get("gitProvider"))
        if provider and not is_full_space_child(provider):
            r.warn(f"gitProvider {provider!r} is not a full `<name>.<space>.<owner>` name")
    if kind == "Workspace" and "isEphemeral" in spec:
        r.warn("isEphemeral: `cordium run/create ws --file` replaces it with the --ephemeral flag")


def check_cluster_config(r: Report, spec: dict[str, Any]) -> None:
    rules = sequence(mapping(mapping(spec.get("space")).get("ownership")).get("rules"))
    if not rules:
        r.warn("space/ownership has no rules: nobody can create additional Spaces; "
               "the automatic personal default Space is still created")
    for idx, rule in enumerate(rules):
        if mapping(rule).get("effect") not in ("ALLOW", "DENY"):
            r.warn(f"space/ownership/rules/{idx}: a rule without ALLOW or DENY is ignored")


def check_document(doc: dict[str, Any], kind: str) -> Report:
    r = Report()
    api = doc.get("apiVersion")
    if api == "core/v1":
        r.error("apiVersion core/v1 is an Octelium resource: manage it with octeliumctl (octelium-management)")
    elif api not in (None, "cordium/v1"):
        r.error(f"apiVersion is {api!r}; Cordium resources use 'cordium/v1'")
    spec = doc.get("spec")
    if kind in ("Workspace", "Template") and not isinstance(spec, dict):
        r.error("spec must be a mapping (use `spec: {}` for an empty one)")
        return r
    spec = mapping(spec)
    if kind == "ClusterConfig":
        r.warn("`cordium man apply` replaces the ENTIRE spec: start from `cordium man get cc -o yaml`")
    elif kind not in ("Workspace", "Template"):
        r.warn(f"no cordium command reads {kind} YAML; it is managed with {CREATED_BY[kind]}")
    r.prefix = "spec/"
    if kind in ("Workspace", "Template"):
        check_spec(r, kind, spec)
    elif kind == "ClusterConfig":
        check_cluster_config(r, spec)
    else:
        if kind == "Space":
            check_runtime(r, spec.get("runtime"), "runtime")
        if kind == "UserConfig":
            for idx, env in enumerate(sequence(spec.get("envVars"))):
                check_env_var(r, env, f"envVars/{idx}", "fromUserSecret")
            check_tasks(r, spec.get("tasks"), "tasks")
            url = text(mapping(spec.get("dotfiles")).get("url"))
            if url and not url.startswith("https://"):
                r.error("dotfiles/url: only https:// URLs are supported")
    r.prefix = ""
    if kind in ("Secret", "UserSecret") and doc.get("data"):
        r.warn("contains plaintext secret data: keep it out of files and git")
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="YAML files, directories (recursive) or - for stdin")
    ap.add_argument("--kind", choices=sorted(KINDS), help="kind for documents that have no `kind` field")
    ap.add_argument("--schema-dir", help="directory with cordium.v1.<Kind>.schema.json files")
    ap.add_argument("--schema-base-url", default=DEFAULT_BASE_URL, help=f"default: {DEFAULT_BASE_URL}")
    ap.add_argument("--offline", action="store_true", help="use the bundled schema snapshot only")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    def fail(err: Exception, code: int) -> int:
        if args.json:
            print(json.dumps({"errors": [str(err)]}, indent=2))
        else:
            print(f"error: {err}", file=sys.stderr)
        return code

    try:
        docs = load_documents(args.paths)
    except (InputError, UnicodeError) as err:
        return fail(err, 1)
    except OSError as err:
        return fail(err, 2)
    source = SchemaSource(args.schema_dir, args.schema_base_url, args.offline)
    results = []
    cluster_configs = 0
    for where, doc in docs:
        kind = doc.get("kind") if "kind" in doc else args.kind
        errors: list[str] = []
        warnings: list[str] = []
        used = None
        if not isinstance(kind, str) or kind not in KINDS:
            if doc.get("apiVersion") == "core/v1":
                errors.append(f"{kind} is an Octelium core/v1 resource: manage it with octeliumctl (octelium-management)")
            elif kind is None:
                errors.append("kind is missing: add `kind: Workspace` (or Template, ClusterConfig) or pass --kind")
            else:
                errors.append(f"unknown kind {kind!r}")
        else:
            cluster_configs += kind == "ClusterConfig"
            if kind == "ClusterConfig" and cluster_configs > 1:
                errors.append("more than one ClusterConfig: `cordium man apply` uses only the first")
            if kind == "ClusterConfig" and "kind" not in doc:
                errors.append("`cordium man apply` needs `kind: ClusterConfig` in the document")
            try:
                loaded = source.get(kind)
                if loaded is None:
                    errors.append(f"no published cordium/v1 schema for {kind}")
                else:
                    schema, used = loaded
                    body = doc if "kind" in doc else {**doc, "kind": kind}
                    errors += schema_errors(schema, body)
            except (OSError, ValueError, jsonschema.exceptions.SchemaError) as err:
                return fail(err, 2)
            report = check_document(doc, kind)
            errors += report.errors
            warnings += report.warnings
        results.append({"where": where, "kind": kind if isinstance(kind, str) else "", "schema": used,
                        "errors": errors, "warnings": warnings})

    n_err = sum(len(r["errors"]) for r in results)
    if args.json:
        print(json.dumps({"documents": results, "errorCount": n_err,
                          "onlineSchemasUnavailable": source.online_failed}, indent=2))
    else:
        if source.online_failed:
            print("note: published schemas unreachable; fell back to the bundled snapshot\n")
        for r in results:
            status = "FAIL" if r["errors"] else ("WARN" if r["warnings"] else "ok")
            print(f"[{status}] {r['kind'] or '?'}  ({r['where']})")
            for e in r["errors"]:
                print(f"    error: {e}")
            for w in r["warnings"]:
                print(f"    warning: {w}")
        print(f"\n{len(results)} document(s), {n_err} error(s)")
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
