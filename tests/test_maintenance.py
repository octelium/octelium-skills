from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import generate_cli_reference as cli
import generate_plugin_manifests as plugins
import maintenance
import sync_schemas as schemas
import validate_repo as validator


class MaintenanceFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="octelium-skills-maintenance-test-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def write_schema(self, directory: Path, kind: str, **fields) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"core.v1.{kind}.schema.json"
        path.write_text(json.dumps({"$schema": schemas.DRAFT, "type": "object", **fields}))
        return path

    def snapshot(self, directory: Path) -> dict[str, bytes]:
        return {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}

    def fake_cli(self, name: str, version: str = "0.43.0", failure: str = "") -> Path:
        binary = self.directory / "bin" / name
        binary.parent.mkdir(exist_ok=True)
        binary.write_text(f"#!{sys.executable}\n" + f'''
import json
import os
import sys
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
settings = {{k: v for k, v in os.environ.items() if k.startswith("OCTELIUM_")}}
if set(settings) != {{"OCTELIUM_HOME"}} or not Path(settings["OCTELIUM_HOME"]).is_dir():
    sys.exit(90)
if args == ["version", "-o", "json"]:
    print(json.dumps({{"releaseVersion": {version!r}}}))
    sys.exit(0)
path = args[:-1]
failure = {failure!r}
if failure == "empty":
    sys.exit(0)
if failure == "malformed":
    print("not command help")
    sys.exit(0)
if path == ["get"] and failure == "child":
    print("Usage:\\n  " + name + " get [flags]")
    sys.exit(7)
if args[-1:] != ["--help"]:
    sys.exit(91)
print("Usage:\\n  " + " ".join([name, *path]) + " [flags]")
if not path:
    print("\\nAvailable Commands:\\n  get  Read resources\\n  help  Help\\n")
''')
        binary.chmod(0o700)
        return binary

    def generate(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with mock.patch.object(cli, "ROOT", self.directory), \
             mock.patch.object(sys, "argv", ["generate", "--bin-dir", str(self.directory / "bin"),
                                             "--version", "v0.43.0", *args]), \
             mock.patch.dict(os.environ, {"OCTELIUM_AUTH_TOKEN": "synthetic-token", "OCTELIUM_DOMAIN": "example.com"}), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = cli.main()
        return result, output.getvalue()

class MaintenanceTests(MaintenanceFixture):
    def test_cli_generation_checks_version_isolation_and_duplicate_outputs(self) -> None:
        self.fake_cli("octops")
        result, output = self.generate("--only", "octops")
        self.assertEqual(result, 0, output)
        copies = [self.directory / "skills" / skill / "references" / "cli-octops.md"
                  for skill in cli.TARGETS["octops"]]
        self.assertEqual(copies[0].read_bytes(), copies[1].read_bytes())
        self.assertIn("Commands: 2", copies[0].read_text())
        self.assertIn("Binary SHA-256:", copies[0].read_text())
        self.assertEqual(self.generate("--only", "octops", "--check")[0], 0)
        copies[0].write_text("old snapshot")
        self.assertEqual(self.generate("--only", "octops", "--check")[0], 1)
        self.assertEqual(copies[0].read_text(), "old snapshot")

    def test_failed_cli_traversal_does_not_write_any_requested_output(self) -> None:
        self.fake_cli("octelium")
        self.fake_cli("octeliumctl", failure="child")
        path = self.directory / "skills/octelium-connect/references/cli-octelium.md"
        path.parent.mkdir(parents=True)
        path.write_text("old snapshot")
        result, output = self.generate("--only", "octelium", "--only", "octeliumctl")
        self.assertEqual(result, 2)
        self.assertIn("octeliumctl get --help: exited with status 7", output)
        self.assertEqual(path.read_text(), "old snapshot")
        self.assertFalse((self.directory / "skills/octelium-management").exists())

    def test_invalid_cli_version_and_help_are_rejected(self) -> None:
        for version, failure, diagnostic in (("0.44.0", "", "differs from reported"),
                                             ("0.43.0", "empty", "malformed Usage"),
                                             ("0.43.0", "malformed", "malformed Usage")):
            with self.subTest(version=version, failure=failure):
                self.fake_cli("octelium", version, failure)
                result, output = self.generate("--only", "octelium")
                self.assertEqual(result, 2)
                self.assertIn(diagnostic, output)
                self.assertFalse((self.directory / "skills").exists())

    def test_cli_timeout_has_command_diagnostic(self) -> None:
        with mock.patch.object(cli.subprocess, "run", side_effect=subprocess.TimeoutExpired("cli", 60)):
            with self.assertRaisesRegex(ValueError, "octelium get --help: timed out"):
                cli.run_help("octelium", ["get"], {})

    def test_help_does_not_append_successful_stderr_to_documentation(self) -> None:
        help_text = "Usage:\n  octelium get [flags]"
        for stdout, stderr in ((help_text, "startup warning"), ("", help_text)):
            with self.subTest(stdout=stdout):
                result = subprocess.CompletedProcess([], 0, stdout, stderr)
                with mock.patch.object(cli.subprocess, "run", return_value=result):
                    self.assertEqual(cli.run_help("octelium", ["get"], {}), help_text)

    def test_file_update_rolls_back_prior_replacements(self) -> None:
        first = self.directory / "first.md"
        second = self.directory / "second.md"
        first.write_text("old first")
        second.write_text("old second")
        replace = os.replace

        def fail_second(src, dest) -> None:
            if dest == second:
                raise OSError("synthetic replace failure")
            replace(src, dest)

        with mock.patch.object(maintenance.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "synthetic replace failure"):
                maintenance.replace_files({first: b"new first", second: b"new second"})
        self.assertEqual(first.read_text(), "old first")
        self.assertEqual(second.read_text(), "old second")
        self.assertEqual(list(self.directory.glob(".octelium-stage-*")), [])

    def test_schema_sync_discovers_new_local_kinds_and_ignores_formatting(self) -> None:
        dest, source = self.directory / "dest", self.directory / "source"
        old = self.write_schema(dest, "Service")
        path = self.write_schema(source, "Service")
        path.write_text(json.dumps(json.loads(path.read_text()), indent=2))
        self.assertEqual(schemas.sync(source, dest, "unused", True), 0)
        self.write_schema(source, "FutureKind")
        self.assertEqual(schemas.sync(source, dest, "unused", True), 1)
        self.assertEqual(list(dest.glob("*")), [old])
        self.assertEqual(schemas.sync(source, dest, "unused", False), 0)
        self.assertEqual(set(schemas.read_snapshot(dest)), {"core.v1.Service.schema.json", "core.v1.FutureKind.schema.json"})

    def test_invalid_or_incomplete_schema_sources_preserve_snapshot(self) -> None:
        dest, source = self.directory / "dest", self.directory / "source"
        self.write_schema(dest, "Service")
        before = self.snapshot(dest)
        for fields in ({"type": "invalid"}, {"$ref": "#/definitions/Missing"}, {"$ref": "https://example.com/schema"}):
            with self.subTest(fields=fields):
                self.write_schema(source, "Service", **fields)
                with self.assertRaises(ValueError):
                    schemas.sync(source, dest, "unused", False)
                self.assertEqual(self.snapshot(dest), before)
        (source / "core.v1.Service.schema.json").unlink()
        self.write_schema(source, "FutureKind")
        with self.assertRaisesRegex(ValueError, "missing bundled schemas"):
            schemas.sync(source, dest, "unused", False)
        self.assertEqual(self.snapshot(dest), before)

    def test_schema_references_support_local_array_and_escaped_pointers(self) -> None:
        self.write_schema(self.directory / "schemas", "Service",
                          allOf=[{"type": "object"}], definitions={"a/b": {"type": "object"}},
                          properties={"first": {"$ref": "#/allOf/0"}, "second": {"$ref": "#/definitions/a~1b"}})
        self.assertIn("core.v1.Service.schema.json", schemas.read_snapshot(self.directory / "schemas"))

    def test_schema_defaults_and_ref_named_properties_are_data(self) -> None:
        self.write_schema(self.directory / "schemas", "Service", properties={"$ref": {"type": "string"}},
                          default={"$ref": "https://example.com"})
        self.assertIn("core.v1.Service.schema.json", schemas.read_snapshot(self.directory / "schemas"))

    def test_remote_failure_is_not_reported_as_drift(self) -> None:
        dest = self.directory / "dest"
        self.write_schema(dest, "Service")
        before = self.snapshot(dest)
        with mock.patch.object(schemas, "DEST", dest), mock.patch.object(sys, "argv", ["sync", "--check"]), \
             mock.patch.object(schemas.subprocess, "run", return_value=subprocess.CompletedProcess([], 28)), \
             contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(schemas.main(), 2)
        self.assertIn("source unavailable", output.getvalue())
        self.assertEqual(self.snapshot(dest), before)

    def test_schema_fetch_bounds_connection_and_total_runtime(self) -> None:
        with mock.patch.object(schemas.subprocess, "run", side_effect=subprocess.TimeoutExpired("curl", 90)) as run:
            with self.assertRaisesRegex(ValueError, "source unavailable"):
                schemas.fetch_schema("https://example.com", "core.v1.Service.schema.json", self.directory / "schema")
        command = run.call_args.args[0]
        self.assertIn("--connect-timeout", command)
        self.assertIn("--max-time", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 90)

    def test_failed_schema_swap_restores_entire_snapshot(self) -> None:
        dest, source = self.directory / "dest", self.directory / "source"
        self.write_schema(dest, "Service")
        self.write_schema(source, "Service", additionalProperties=False)
        before = self.snapshot(dest)
        rename = Path.rename

        def fail_stage(path, target):
            if path.parent.name.startswith(".octelium-schema-stage-"):
                raise OSError("synthetic rename failure")
            return rename(path, target)

        with mock.patch.object(Path, "rename", fail_stage):
            with self.assertRaisesRegex(OSError, "synthetic rename failure"):
                schemas.sync(source, dest, "unused", False)
        self.assertEqual(self.snapshot(dest), before)
        self.assertEqual(list(self.directory.glob(".octelium-schema-*")), [])


class RepositoryValidationTests(MaintenanceFixture):
    def setUp(self) -> None:
        super().setUp()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(validator, "ROOT", self.directory).start()
        mock.patch.object(validator, "SKILLS", self.directory / "skills").start()
        mock.patch.object(validator, "SCHEMAS", self.directory / "schemas").start()
        (self.directory / "skills/test/references").mkdir(parents=True)
        self.write_schema(self.directory / "schemas", "Service")
        validator.errors.clear()
        validator.warnings.clear()

    def test_malformed_frontmatter_is_rejected_without_crashing(self) -> None:
        for body in ("[broken", "- list", "42", "null"):
            with self.subTest(body=body):
                self.assertIsNone(validator.split_frontmatter(f"---\n{body}\n---\nbody"))

    def test_unknown_kind_and_api_and_unclassified_fragment_fail(self) -> None:
        path = self.directory / "skills/test/references/example.md"
        for example in ("kind: Servcie", "kind: Service\napiVersion: core/v2", "spec: {}", "- kind: Service"):
            with self.subTest(example=example):
                validator.errors.clear()
                path.write_text(f"```yaml\n{example}\n```\n")
                validator.check_yaml_examples()
                self.assertTrue(validator.errors)
                self.assertTrue(any("yaml block 1" in error for error in validator.errors))

    def test_explicit_external_fragment_and_bootstrap_are_parsed(self) -> None:
        path = self.directory / "skills/test/references/example.md"
        path.write_text("```yaml\nkind: Service\n```\n"
                        "```yaml kubernetes\napiVersion: cert-manager.io/v1\nkind: Certificate\n```\n"
                        "```yaml fragment\nconfig: {}\n```\n"
                        "```yaml bootstrap\nspec: {}\n```\n")
        bootstrap = self.directory / "skills/test/assets/bootstrap.example.yaml"
        bootstrap.parent.mkdir()
        bootstrap.write_text("spec: [invalid\n")
        validator.check_yaml_examples()
        self.assertEqual(len(validator.errors), 1)
        self.assertIn("bootstrap.example.yaml", validator.errors[0])
        bootstrap.write_text("spec: {}\n")
        validator.errors.clear()
        validator.check_yaml_examples()
        self.assertEqual(validator.errors, [])

    def prepare_manifests(self) -> dict:
        for path in ("plugin.json", ".codex-plugin/plugin.json", ".claude-plugin/plugin.json",
                     ".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json",
                     "scripts/schemas/agent-plugins-1.0.0.schema.json"):
            dest = self.directory / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)
        return json.loads((self.directory / "plugin.json").read_text())

    def test_portable_and_compatibility_layouts_agree(self) -> None:
        portable = self.prepare_manifests()
        validator.check_manifests()
        self.assertEqual(validator.errors, [])
        expected = plugins.compatibility_manifests(portable)
        self.assertEqual(expected[".codex-plugin/plugin.json"]["interface"], portable["extensions"]["com.openai"]["interface"])
        portable["version"] = "0.2.0"
        (self.directory / "plugin.json").write_text(json.dumps(portable))
        validator.check_manifests()
        self.assertTrue(any("generate_plugin_manifests.py" in e for e in validator.errors))

    def test_portable_components_cannot_be_overridden_in_extension(self) -> None:
        portable = self.prepare_manifests()
        portable["extensions"]["com.openai"]["skills"] = "./other-skills/"
        with self.assertRaisesRegex(ValueError, "must not override"):
            plugins.compatibility_manifests(portable)

    def test_malformed_manifests_produce_diagnostics(self) -> None:
        for path, value in (("plugin.json", []), (".agents/plugins/marketplace.json", {"plugins": [42]}),
                            (".claude-plugin/marketplace.json", {"plugins": ["bad"]})):
            with self.subTest(path=path):
                self.prepare_manifests()
                validator.errors.clear()
                (self.directory / path).write_text(json.dumps(value))
                validator.check_manifests()
                self.assertTrue(validator.errors)

    def test_missing_dependencies_fail_with_environment_exit_code(self) -> None:
        for script, dependency in (("validate_repo.py", "yaml"), ("validate_repo.py", "jsonschema"),
                                   ("sync_schemas.py", "jsonschema")):
            with self.subTest(script=script, dependency=dependency):
                code = ("import runpy,sys; sys.path.insert(0,sys.argv[1]); "
                        "sys.modules[sys.argv[3]]=None; runpy.run_path(sys.argv[2],run_name='__main__')")
                result = subprocess.run([sys.executable, "-c", code, str(ROOT / "scripts"),
                                         str(ROOT / "scripts" / script), dependency],
                                        capture_output=True, text=True, timeout=30, check=False)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("required", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
