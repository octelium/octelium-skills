from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "cordium" / "scripts" / "validate_resources.py"
TEMPLATES = ROOT / "skills" / "cordium" / "assets" / "templates"


class CordiumValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="octelium-skills-cordium-test-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

    def write_yaml(self, text: str, name: str = "spec.yaml") -> Path:
        path = self.directory / name
        path.write_text(text)
        return path

    def validate(self, *args: object, text: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SCRIPT), "--offline", "--json", *(str(a) for a in args)],
                              input=text, capture_output=True, text=True, env=self.env, timeout=30, check=False)

    def document(self, *args: object, text: str | None = None) -> tuple[int, dict]:
        result = self.validate(*args, text=text)
        self.assertNotIn("Traceback", result.stderr + result.stdout)
        report = json.loads(result.stdout)
        self.assertIn("documents", report, report)
        self.assertEqual(len(report["documents"]), 1)
        return result.returncode, report["documents"][0]

    def assert_messages(self, messages: list[str], *fragments: str) -> None:
        for fragment in fragments:
            self.assertTrue(any(fragment in m for m in messages), f"{fragment!r} not in {messages}")

    def test_bundled_templates_have_no_errors(self) -> None:
        result = self.validate(TEMPLATES)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["errorCount"], 0)
        self.assertEqual({d["kind"] for d in report["documents"]}, {"Workspace", "Template", "ClusterConfig"})

    def test_unknown_fields_and_documented_mistakes_are_errors(self) -> None:
        path = self.write_yaml(
            "kind: Workspace\nspec:\n"
            "  image:\n    git:\n      url: https://github.com/org/images\n      cloneOptions: {checkout: main}\n"
            "  vars:\n    - name: TURNS\n      defaultValue: '80'\n")
        code, doc = self.document(path)
        self.assertEqual(code, 1)
        self.assert_messages(doc["errors"], "'cloneOptions' was unexpected", "'defaultValue' was unexpected")

    def test_api_server_checks_are_mirrored(self) -> None:
        path = self.write_yaml("""kind: Workspace
spec:
  repository:
    url: git@github.com:org/repo.git
  runtime:
    envVars:
      - key: EMPTY
        value: ""
      - key: NOTHING
    tasks:
      - name: build
        run: make
    network:
      egress:
        rules:
          - action: ALLOW
            cidrs: ["10.0.0.1/8"]
            ports: [0]
    volumeMounts:
      - volumeRef: {name: data}
        mountPath: /etc
      - volumeRef: {name: cache}
        mountPath: /data/
  applications:
    - {name: web, port: 3000, isDefault: true}
    - {name: api, port: 8080, isDefault: true}
""")
        code, doc = self.document(path)
        self.assertEqual(code, 1)
        self.assert_messages(doc["errors"], "only https:// repository URLs", "empty value for EMPTY",
                             "no value or fromSecret for NOTHING", "type must be ON_CREATE",
                             "not a canonical CIDR", "invalid port 0", "/etc is reserved",
                             "clean canonical path", "at most one application can be isDefault")

    def test_variables_in_validated_git_fields_are_rejected(self) -> None:
        path = self.write_yaml("""kind: Workspace
spec:
  vars:
    - {name: BRANCH, value: main}
  repository:
    url: ${{ vars.REPO }}
    cloneOptions:
      branch: ${{ vars.BRANCH }}
  additionalRepositories:
    - name: shared
      repository:
        url: https://github.com/${{vars.ORG}}/shared
""")
        code, doc = self.document(path)
        self.assertEqual(code, 1)
        self.assert_messages(doc["errors"], "spec/repository/url: the API validates the URL",
                             "spec/repository/cloneOptions/branch: the API validates it")
        self.assertFalse(any("additionalRepositories" in e for e in doc["errors"]), doc["errors"])
        self.assert_messages(doc["warnings"], "ORG is not defined here", "REPO is not defined here")

    def test_variable_references_are_linted(self) -> None:
        path = self.write_yaml("""kind: Template
spec:
  vars:
    - {name: TASK, value: test}
  image:
    dockerfile:
      inline: "FROM node:${{ vars.NODE }}"
  runtime:
    tasks:
      - name: run
        type: POST_START
        run: echo "${{ vars.TASK }}" ${{vars.TASK }}
""")
        code, doc = self.document(path)
        self.assertEqual(code, 0, doc)
        self.assert_messages(doc["warnings"], "spec/image/dockerfile/inline: variables are not substituted",
                             "is not a `${{ vars.NAME }}` reference and is removed")
        self.assertFalse(any("TASK is not defined" in w for w in doc["warnings"]), doc["warnings"])

    def test_short_references_and_ignored_fields_warn(self) -> None:
        path = self.write_yaml("""kind: Template
spec:
  gitProvider: github.my-project
  repository:
    url: https://github.com/org/repo
    authentication:
      http:
        username: oauth2
        password: {fromSecret: pat}
  additionalRepositories:
    - name: shared
      clonePath: /opt/shared
      repository: {url: https://github.com/org/shared}
  runtime:
    envVars:
      - {key: API_KEY, fromSecret: api-key.my-project}
    timeout: {mode: DISABLED}
    octelium: {serveAll: true}
    capabilities: {add: [SYS_ADMIN]}
""")
        code, doc = self.document(path)
        self.assertEqual(code, 0, doc)
        self.assert_messages(doc["warnings"], "gitProvider 'github.my-project' is not a full",
                             "fromSecret 'pat' is not a full", "fromSecret 'api-key.my-project' is not a full",
                             "clonePath: ignored", "ignored in Templates", "serves its owner's Octelium Services",
                             "SYS_ADMIN widens")

    def test_full_secret_names_do_not_warn(self) -> None:
        path = self.write_yaml("kind: Workspace\nspec:\n  runtime:\n    envVars:\n"
                               "      - {key: API_KEY, fromSecret: api-key.agents.alice}\n")
        code, doc = self.document(path)
        self.assertEqual((code, doc["errors"], doc["warnings"]), (0, [], []))

    def test_missing_kind_needs_the_kind_flag(self) -> None:
        path = self.write_yaml("spec:\n  image:\n    registry: {url: python:3.12}\n")
        code, doc = self.document(path)
        self.assertEqual(code, 1)
        self.assert_messages(doc["errors"], "kind is missing")
        code, doc = self.document("--kind", "Workspace", path)
        self.assertEqual((code, doc["kind"], doc["errors"]), (0, "Workspace", []))

    def test_workspace_needs_a_spec_mapping(self) -> None:
        for text in ("kind: Workspace\n", "kind: Workspace\nspec: []\n"):
            with self.subTest(text=text):
                code, doc = self.document(self.write_yaml(text))
                self.assertEqual(code, 1)
                self.assert_messages(doc["errors"], "spec must be a mapping")

    def test_cluster_config_risks(self) -> None:
        path = self.write_yaml("""kind: ClusterConfig
spec:
  workspace:
    storage:
      storageClass:
        rules:
          - condition: {match: ctx.workspace.spec.isEphemeral}
            storageClass: fast
    timeout:
      maxActiveDuration: {days: 1}
""")
        code, doc = self.document(path)
        self.assertEqual(code, 0, doc)
        self.assert_messages(doc["warnings"], "replaces the ENTIRE spec", "nobody can create Spaces",
                             "only matchAny", "maxActiveDuration is not enforced")

    def test_cluster_config_is_a_singleton_with_kind(self) -> None:
        path = self.write_yaml("kind: ClusterConfig\nspec: {}\n---\nkind: ClusterConfig\nspec: {}\n")
        result = self.validate(path)
        self.assertEqual(result.returncode, 1)
        errors = json.loads(result.stdout)["documents"][1]["errors"]
        self.assert_messages(errors, "more than one ClusterConfig")
        code, doc = self.document("--kind", "ClusterConfig", self.write_yaml("spec: {}\n", "cc.yaml"))
        self.assertEqual(code, 1)
        self.assert_messages(doc["errors"], "needs `kind: ClusterConfig`")

    def test_other_kinds_explain_how_they_are_managed(self) -> None:
        code, doc = self.document("-", text="kind: Volume\nspec: {size: {megabytes: 2000}}\n")
        self.assertEqual(code, 0, doc)
        self.assert_messages(doc["warnings"], "no cordium command reads Volume YAML", "`cordium create volume`")
        code, doc = self.document("-", text="kind: Secret\nspec: {}\ndata: {value: synthetic}\n")
        self.assert_messages(doc["warnings"], "plaintext secret data")

    def test_octelium_resources_are_redirected(self) -> None:
        code, doc = self.document("-", text="apiVersion: core/v1\nkind: Service\nmetadata: {name: web}\nspec: {}\n")
        self.assertEqual(code, 1)
        self.assert_messages(doc["errors"], "Octelium core/v1 resource")

    def test_invalid_input_fails_cleanly(self) -> None:
        for text in ("kind: Workspace\nspec:\n  image: {}\n  image: {}\n", "- kind: Workspace\n", "spec: [\n"):
            with self.subTest(text=text):
                result = self.validate("-", text=text)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertTrue(json.loads(result.stdout)["errors"])
                self.assertNotIn("Traceback", result.stderr)
        result = self.validate(self.directory / "missing.yaml")
        self.assertEqual(result.returncode, 2)

    def test_schema_dir_without_the_kind_reports_it(self) -> None:
        schemas = self.directory / "schemas"
        schemas.mkdir()
        code, doc = self.document("--schema-dir", schemas, "-", text="kind: Workspace\nspec: {}\n")
        self.assertEqual(code, 1)
        self.assert_messages(doc["errors"], "no published cordium/v1 schema for Workspace")


if __name__ == "__main__":
    unittest.main()
