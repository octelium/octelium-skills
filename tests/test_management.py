from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "octelium-management" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from _common import InputError, load_documents, resolve_kinds
from export_resources import main as export_main
from plan_apply import CtlError, run_ctl, spec_diff


FAKE_CTL = '''
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["OCTELIUM_TEST_REQUESTS"], "a") as stream:
    stream.write(json.dumps(args) + "\\n")
if args[0] != "get":
    sys.exit(99)
page = args[args.index("--page") + 1] if "--page" in args else "0"
with open(os.environ["OCTELIUM_TEST_RESPONSES"]) as stream:
    responses = json.load(stream)
response = responses.get(args[1] + ":" + page, {"items": []})
if isinstance(response, dict) and "error" in response:
    print(response["error"], file=sys.stderr)
    sys.exit(1)
print(response if isinstance(response, str) else json.dumps(response))
'''


def resource(kind: str, name: str, **extra: object) -> dict:
    return {"kind": kind, "metadata": {"name": name}, "spec": {}, **extra}


class ManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="octelium-skills-test-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.ctl = self.directory / "octeliumctl"
        self.ctl.write_text(f"#!{sys.executable}\n" + FAKE_CTL)
        self.ctl.chmod(0o700)
        self.requests = self.directory / "requests.jsonl"
        self.responses = self.directory / "responses.json"
        self.responses.write_text("{}")
        self.env = {**os.environ, "OCTELIUM_DOMAIN": "example.com", "PYTHONDONTWRITEBYTECODE": "1",
                    "OCTELIUM_TEST_REQUESTS": str(self.requests), "OCTELIUM_TEST_RESPONSES": str(self.responses),
                    "PATH": str(self.directory) + os.pathsep + os.environ.get("PATH", "")}

    def write_yaml(self, text: str, name: str = "resources.yaml") -> Path:
        path = self.directory / name
        path.write_text(text)
        return path

    def set_responses(self, responses: dict) -> None:
        self.responses.write_text(json.dumps(responses))

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.requests.read_text().splitlines()] if self.requests.exists() else []

    def run_script(self, name: str, *args: object, text: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)],
                              input=text, capture_output=True, text=True, env=self.env, timeout=30, check=False)

    def plan(self, *paths: object, flags: tuple[str, ...] = (), text: str | None = None) -> subprocess.CompletedProcess:
        return self.run_script("plan_apply.py", "--json", "--octeliumctl", self.ctl, *flags, *paths, text=text)

    def assert_input_error(self, result: subprocess.CompletedProcess) -> None:
        self.assertEqual(result.returncode, 1, result.stderr + result.stdout)
        self.assertTrue(json.loads(result.stdout)["errors"])
        self.assertNotIn("Traceback", result.stderr + result.stdout)
        self.assertEqual(self.calls(), [])

    def test_missing_and_unknown_kinds_fail_before_reads(self) -> None:
        for text in ("metadata: {name: ops}\n", "kind: Bogus\nmetadata: {name: ops}\n", "kind: true\n"):
            with self.subTest(text=text):
                self.assert_input_error(self.plan(self.write_yaml(text)))

    def test_duplicate_resources_fail_before_reads(self) -> None:
        path = self.write_yaml("kind: Group\nmetadata: {name: ops}\n---\nkind: Group\nmetadata: {name: ops}\n")
        self.assert_input_error(self.plan(path, flags=("--prune",)))

    def test_duplicate_services_normalize_across_files_and_stdin(self) -> None:
        first = self.write_yaml("kind: Service\nmetadata: {name: web}\n")
        text = "kind: Service\nmetadata: {name: web.default}\n"
        second = self.write_yaml(text, "second.yaml")
        for paths, stdin in (((first, second), None), ((first, "-"), text)):
            with self.subTest(paths=paths):
                self.assert_input_error(self.plan(*paths, text=stdin))

    def test_cluster_config_is_a_singleton(self) -> None:
        path = self.write_yaml("kind: ClusterConfig\nmetadata: {name: first}\n---\nkind: ClusterConfig\nmetadata: {name: second}\n")
        self.assert_input_error(self.plan(path))
        result = self.run_script("validate_resources.py", path, "--offline", "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        errors = json.loads(result.stdout)["documents"][1]["errors"]
        self.assertTrue(any("duplicate ClusterConfig" in err for err in errors))

    def test_invalid_shapes_fail_cleanly(self) -> None:
        for text in ("kind: Group\nmetadata: wrong\n", "kind: Group\nmetadata: {name: true}\n",
                     "kind: Group\nmetadata: {name: 12}\n", "kind: Group\nmetadata: {name: ops}\nspec: wrong\n"):
            with self.subTest(text=text):
                path = self.write_yaml(text)
                self.assert_input_error(self.plan(path))
                result = self.run_script("validate_resources.py", path, "--offline", "--json")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertGreater(json.loads(result.stdout)["errorCount"], 0)
                self.assertNotIn("Traceback", result.stderr)

    def test_nested_authorization_shapes_do_not_crash_lint(self) -> None:
        for auth in ("wrong", {"policies": 5}, {"inlinePolicies": "wrong"}, {"inlinePolicies": ["wrong"]},
                     {"inlinePolicies": [{"spec": "wrong"}]}, {"inlinePolicies": [{"spec": {"rules": [True]}}]},
                     {"inlinePolicies": [{"spec": {"rules": [{"effect": "ALLOW", "condition": "wrong"}]}}]}):
            with self.subTest(auth=auth):
                body = resource("Group", "ops", spec={"authorization": auth})
                result = self.run_script("validate_resources.py", self.write_yaml(yaml.safe_dump(body)), "--offline", "--json")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertGreater(json.loads(result.stdout)["errorCount"], 0)
                self.assertNotIn("Traceback", result.stderr)

    def test_nested_duplicate_mapping_keys_are_rejected(self) -> None:
        path = self.write_yaml("kind: User\nmetadata: {name: alice}\nspec:\n  isDisabled: true\n  isDisabled: false\n")
        self.assert_input_error(self.plan(path))
        result = self.run_script("validate_resources.py", path, "--offline", "--json")
        self.assert_input_error(result)
        self.assertIn("duplicate key", result.stdout)

    def test_scalar_names_follow_go_yaml_mapping_behavior(self) -> None:
        for name in ("on", "off", "yes", "no"):
            with self.subTest(name=name):
                path = self.write_yaml(f"kind: Group\nmetadata: {{name: {name}}}\n")
                self.assertEqual(load_documents([str(path)])[0].name, name)
                result = self.run_script("validate_resources.py", path, "--offline", "--json")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIs(yaml.safe_load("on"), True)

    def test_empty_documents_aliases_and_merge_keys(self) -> None:
        path = self.write_yaml("---\n---\nkind: Group\nmetadata: &meta {name: ops}\nspec:\n  attrs: {copy: *meta}\n")
        docs = load_documents([str(path)])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0].body["spec"]["attrs"]["copy"], {"name": "ops"})
        path = self.write_yaml("kind: Group\nmetadata: {name: ops}\nspec:\n  attrs:\n    <<: &attrs {enabled: true}\n    enabled: false\n")
        self.assertIs(load_documents([str(path)])[0].body["spec"]["attrs"]["enabled"], False)
        with self.assertRaises(InputError):
            load_documents([str(self.write_yaml("---\n\n"))])

    def test_non_json_yaml_values_fail_cleanly(self) -> None:
        for text in ("kind: Group\nmetadata: {name: ops}\nspec: {attrs: {value: .nan}}\n",
                     "kind: Group\nmetadata: {name: ops}\nspec: {attrs: {value: !!set {one: null}}}\n",
                     "kind: Group\nmetadata: {name: ops}\nspec: &spec {attrs: *spec}\n"):
            with self.subTest(text=text):
                self.assert_input_error(self.plan(self.write_yaml(text)))

    def test_case_insensitive_discovery_and_symlink_rules(self) -> None:
        root = self.directory / "tree"
        root.mkdir()
        path = root / "desired.YAML"
        path.write_text("kind: Group\nmetadata: {name: ops}\n")
        (root / "linked.yml").symlink_to(path)
        (root / "ignored.txt").write_text("invalid YAML")
        outside = self.directory / "outside"
        outside.mkdir()
        (outside / "hidden.yaml").write_text("kind: User\nmetadata: {name: alice}\n")
        (root / "linked-directory").symlink_to(outside, target_is_directory=True)
        self.assertEqual([doc.name for doc in load_documents([str(root)])], ["ops"])
        self.assertEqual(load_documents([str(root / "linked.yml")])[0].name, "ops")
        with self.assertRaises(InputError):
            load_documents([str(root / "linked-directory")])

    def test_comma_separated_and_repeated_kind_flags(self) -> None:
        self.assertEqual(resolve_kinds(["Group,User", "Service"], ["User"], False), ["Group", "Service"])
        path = self.write_yaml("kind: Group\nmetadata: {name: ops}\n")
        result = self.plan(path, flags=("--include", "Group,User"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["kinds"], ["Group", "User"])
        bad = self.plan(path, flags=("--include", "Bogus"))
        self.assertEqual(bad.returncode, 2, bad.stderr)
        self.assertTrue(json.loads(bad.stdout)["errors"])

    def test_valid_excluded_kinds_are_skipped(self) -> None:
        path = self.write_yaml("kind: User\nmetadata: {name: alice}\n---\nkind: Session\nmetadata: {name: session}\n")
        result = self.plan(path, flags=("--include", "Service"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["skipped"]), 2)
        self.assertEqual(self.calls(), [])

    def test_missing_files_return_json_environment_errors(self) -> None:
        for script in ("validate_resources.py", "plan_apply.py"):
            with self.subTest(script=script):
                result = self.run_script(script, self.directory / "missing.yaml", "--json")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertTrue(json.loads(result.stdout)["errors"])
                self.assertNotIn("Traceback", result.stderr)

    def test_invalid_schema_file_returns_json_environment_error(self) -> None:
        schema = self.directory / "core.v1.Group.schema.json"
        for text in ("{invalid", '["invalid schema"]'):
            with self.subTest(text=text):
                schema.write_text(text)
                path = self.write_yaml("kind: Group\nmetadata: {name: ops}\n")
                result = self.run_script("validate_resources.py", path, "--schema-dir", self.directory, "--json")
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertTrue(json.loads(result.stdout)["errors"])

    def test_invalid_json_and_list_shapes_return_environment_errors(self) -> None:
        path = self.write_yaml("kind: Group\nmetadata: {name: ops}\n")
        for response in ('{"items":', {"items": "wrong"}, {"items": [True]},
                         {"items": [{"metadata": "wrong"}]}, {"items": [], "listResponseMeta": "wrong"},
                         {"items": [], "listResponseMeta": {"hasMore": True}}):
            with self.subTest(response=response):
                self.set_responses({"group:1": response})
                result = self.plan(path)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertTrue(json.loads(result.stdout)["errors"])
                self.assertNotIn("Traceback", result.stderr)

    def test_failed_and_timed_out_subprocesses_raise_ctl_errors(self) -> None:
        for error in (OSError("cannot execute"), subprocess.TimeoutExpired("octeliumctl", 120)):
            with self.subTest(error=error), patch("plan_apply.subprocess.run", side_effect=error):
                with self.assertRaises(CtlError):
                    run_ctl("octeliumctl", "example.com", ["get", "group"])

    def test_comparison_preserves_intentional_data_and_status_omission(self) -> None:
        current = resource("Config", "app-config", data={"value": "old"}, status={"version": 1})
        desired = resource("Config", "app-config", data={"value": "new"}, status={"version": 2})
        self.assertFalse(any(spec_diff(desired, current).values()))

    def test_plan_paginates_and_flags_prune_dangers(self) -> None:
        self.set_responses({"group:1": {"items": [resource("Group", "ops")], "listResponseMeta": {"hasMore": True}},
                            "group:2": {"items": [resource("Group", "old-team")]}})
        path = self.write_yaml("kind: Group\nmetadata: {name: ops}\n")
        result = self.plan(path, flags=("--prune", "--include", "Group"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["delete"], [{"kind": "Group", "name": "old-team"}])
        self.assertEqual([call[call.index("--page") + 1] for call in self.calls()], ["1", "2"])
        self.set_responses({"user:1": {"items": [resource("User", "root")]}})
        result = self.plan(path, flags=("--prune", "--include", "User"))
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertTrue(json.loads(result.stdout)["dangers"])

    def test_allow_all_warnings_respect_holder_scope(self) -> None:
        for kind, expected in (("Service", "this Service"), ("Namespace", "this Namespace"),
                               ("Group", "every Service, including the Octelium API")):
            with self.subTest(kind=kind):
                body = resource(kind, "example", spec={"authorization": {"policies": ["allow-all"]}})
                path = self.write_yaml(yaml.safe_dump(body))
                result = self.run_script("validate_resources.py", path, "--offline", "--json")
                warnings = json.loads(result.stdout)["documents"][0]["warnings"]
                self.assertTrue(any(expected in warning for warning in warnings))
                if kind in ("Service", "Namespace"):
                    self.assertFalse(any("including the Octelium API" in warning for warning in warnings))

    def export_fixture(self) -> dict:
        config = resource("Config", "app-config", data={"value": "on"})
        config["metadata"].update({"uid": "old-uid", "resourceVersion": "old-version", "labels": {"team": "ops"}})
        config["status"] = {"server": "old-server"}
        service = resource("Service", "web.default", spec={"mode": "HTTP", "authorization": {"policies": ["team-policy"]}})
        service["metadata"]["createdAt"] = "2026-10-05"
        system = resource("Namespace", "default")
        system["metadata"]["isSystem"] = True
        hidden = resource("Namespace", "hidden")
        hidden["metadata"]["isSystemHidden"] = True
        return {"config:1": {"items": [config], "listResponseMeta": {"hasMore": True}},
                "config:2": {"items": [resource("Config", "another-config", data={"valueBytes": "ZGF0YQ=="}),
                                        resource("Config", "structured-config", data={"attrs": {"enabled": True}})]},
                "policy:1": "No Policies found", "namespace:1": {"items": [system, hidden, resource("Namespace", "production")]},
                "service:1": {"items": [service]},
                "clusterconfig:0": resource("ClusterConfig", "default", spec={"session": {"human": {"maxPerUser": 5}}}),
                "cc:0": resource("ClusterConfig", "default", spec={"session": {"human": {"maxPerUser": 5}}})}

    def assert_export(self, documents: list[dict]) -> None:
        self.assertEqual([(doc["kind"], doc["metadata"]["name"]) for doc in documents],
                         [("Config", "app-config"), ("Config", "another-config"), ("Config", "structured-config"), ("Namespace", "production"),
                          ("Service", "web.default"), ("ClusterConfig", "default")])
        self.assertEqual(documents[0]["data"], {"value": "on"})
        self.assertEqual(documents[1]["data"], {"valueBytes": "ZGF0YQ=="})
        self.assertEqual(documents[2]["data"], {"attrs": {"enabled": True}})
        self.assertEqual(documents[4]["spec"]["authorization"]["policies"], ["team-policy"])
        for doc in documents:
            self.assertNotIn("status", doc)
            self.assertFalse({"uid", "resourceVersion", "createdAt", "isSystem", "isSystemHidden"} & doc["metadata"].keys())
        self.assertTrue(all(call[0] == "get" for call in self.calls()))
        self.assertFalse(any(call[1] in ("secret", "credential") for call in self.calls()))

    def test_export_is_paginated_portable_and_apply_ready(self) -> None:
        self.set_responses(self.export_fixture())
        result = self.run_script("export_resources.py", "--octeliumctl", self.ctl)
        self.assertEqual(result.returncode, 0, result.stderr)
        documents = list(yaml.safe_load_all(result.stdout))
        self.assert_export(documents)
        path = self.write_yaml(result.stdout)
        result = self.run_script("validate_resources.py", path, "--offline", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_export_failure_writes_no_partial_stream(self) -> None:
        fixture = self.export_fixture()
        fixture["config:2"] = {"error": "synthetic read failure"}
        self.set_responses(fixture)
        result = self.run_script("export_resources.py", "--octeliumctl", self.ctl)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_export_selected_kinds_and_empty_lists(self) -> None:
        result = self.run_script("export_resources.py", "--include", "Group,User", "--skip-cluster-config", "--octeliumctl", self.ctl)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual([call[1] for call in self.calls()], ["group", "user"])
        result = self.run_script("export_resources.py", "--include", "Secret", "--octeliumctl", self.ctl)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_export_in_process_failure_reports_only_error(self) -> None:
        output, errors = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env), patch.object(sys, "argv", ["export_resources.py"]), \
                patch("export_resources.export_resources", side_effect=CtlError("failed")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(export_main(), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("failed", errors.getvalue())

    def test_standalone_export_recipe(self) -> None:
        path = ROOT / "skills" / "octelium-quick-install" / "references" / "recovery-and-removal.md"
        recipe = re.findall(r"```bash\n(.*?)\n```", path.read_text(), re.S)[-1]
        self.set_responses(self.export_fixture())
        result = subprocess.run(["bash", "-c", recipe], cwd=self.directory, env=self.env,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        export_file = self.directory / result.stdout.strip()
        self.assertEqual(stat.S_IMODE(export_file.stat().st_mode), 0o600)
        self.assert_export(list(yaml.safe_load_all(export_file.read_text())))

    def test_standalone_export_failure_removes_partial_file(self) -> None:
        path = ROOT / "skills" / "octelium-quick-install" / "references" / "recovery-and-removal.md"
        recipe = re.findall(r"```bash\n(.*?)\n```", path.read_text(), re.S)[-1]
        fixture = self.export_fixture()
        fixture["config:2"] = {"error": "synthetic read failure"}
        self.set_responses(fixture)
        result = subprocess.run(["bash", "-c", recipe], cwd=self.directory, env=self.env,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(list(self.directory.glob("octelium-config.*.yaml")), [])


class PolicyRecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        path = ROOT / "skills" / "octelium-management" / "references" / "policies.md"
        examples = [yaml.safe_load(block) for block in re.findall(r"```yaml\n(.*?)\n```", path.read_text(), re.S)]
        self.policy = next(body for body in examples if body.get("metadata", {}).get("name") == "contractors-read-only")

    def decision(self, method: str, groups: list[str], additional: list[dict] | None = None) -> str | None:
        enforcement = self.policy["spec"]["enforcementRules"][0]["condition"]["not"]
        group = ast.literal_eval(enforcement.split(" in ctx.user.spec.groups")[0])
        if group not in groups:
            return None
        matches = []
        for rule in self.policy["spec"]["rules"] + (additional or []):
            condition = rule["condition"]
            expression = condition.get("match", "")
            matches_method = expression.startswith("ctx.request.http.method in ") and method in ast.literal_eval(expression.split(" in ")[1])
            if condition.get("matchAny") or matches_method:
                matches.append((rule.get("priority", 0), 0 if rule["effect"] == "DENY" else 1, rule["effect"]))
        return min(matches)[2] if matches else "DENY"

    def test_contractors_read_methods_are_allowed(self) -> None:
        for method in ("GET", "HEAD", "OPTIONS"):
            with self.subTest(method=method):
                self.assertEqual(self.decision(method, ["contractors"]), "ALLOW")

    def test_contractors_write_methods_are_denied(self) -> None:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(method=method):
                self.assertEqual(self.decision(method, ["contractors"]), "DENY")

    def test_non_contractors_are_ignored(self) -> None:
        for method in ("GET", "POST"):
            with self.subTest(method=method):
                self.assertIsNone(self.decision(method, ["ops"]))

    def test_rule_order_does_not_change_decisions(self) -> None:
        self.policy["spec"]["rules"].reverse()
        self.assertEqual(self.decision("GET", ["contractors"]), "ALLOW")
        self.assertEqual(self.decision("POST", ["contractors"]), "DENY")

    def test_higher_priority_rules_and_deny_ties(self) -> None:
        for priority, effect, method, expected in ((-2, "DENY", "GET", "DENY"), (-2, "ALLOW", "POST", "ALLOW"),
                                                 (-1, "DENY", "GET", "DENY"), (0, "ALLOW", "POST", "DENY")):
            with self.subTest(priority=priority, effect=effect):
                rule = {"priority": priority, "effect": effect, "condition": {"matchAny": True}}
                self.assertEqual(self.decision(method, ["contractors"], [rule]), expected)


if __name__ == "__main__":
    unittest.main()
