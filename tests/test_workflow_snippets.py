from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ProtectedWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="octelium-skills-workflow-test-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.env = {**os.environ, "PATH": str(self.directory) + os.pathsep + os.environ.get("PATH", ""),
                    "PYTHONDONTWRITEBYTECODE": "1", "OCTELIUM_TEST_DIR": str(self.directory)}

    def fake_command(self, name: str, body: str) -> None:
        path = self.directory / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o700)

    def recipe(self, skill: str, file: str, index: int = -1) -> str:
        path = ROOT / "skills" / skill / "references" / file
        return re.findall(r"```bash\n(.*?)\n[ \t]*```", path.read_text(), re.S)[index]

    def run_recipe(self, recipe: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-c", "umask 022\n" + recipe], cwd=self.directory,
                              env=self.env, capture_output=True, text=True, timeout=30, check=False)

    def protected_output_command(self, name: str) -> None:
        self.fake_command(name, '''
import os
import stat
import sys

if stat.S_IMODE(os.fstat(sys.stdout.fileno()).st_mode) != 0o600:
    sys.exit(98)
print("synthetic-private-output")
sys.exit(int(os.environ.get("OCTELIUM_TEST_FAILURE", "0")))
''')

    def test_dump_and_credential_capture_are_private_before_write(self) -> None:
        cases = (("kubectl", "octelium-quick-install", "post-install.md", -1),
                 ("octeliumctl", "octelium-management", "identity-and-access.md", 1))
        for command, skill, file, index in cases:
            with self.subTest(command=command):
                self.protected_output_command(command)
                result = self.run_recipe(self.recipe(skill, file, index))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn("synthetic-private-output", result.stdout)
                path = self.directory / result.stdout.strip()
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(path.read_text().strip(), "synthetic-private-output")
                path.unlink()

    def test_failed_dump_and_credential_capture_remove_partial_files(self) -> None:
        self.env["OCTELIUM_TEST_FAILURE"] = "1"
        cases = (("kubectl", "octelium-quick-install", "post-install.md", "octelium-backup.*.sql", -1),
                 ("octeliumctl", "octelium-management", "identity-and-access.md", "octelium-credential.*.json", 1))
        for command, skill, file, pattern, index in cases:
            with self.subTest(command=command):
                self.protected_output_command(command)
                result = self.run_recipe(self.recipe(skill, file, index))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(list(self.directory.glob(pattern)), [])

    def test_export_helper_uses_installed_path_and_preserves_project_directory(self) -> None:
        skill = self.directory / "installed skill"
        script = skill / "scripts/export_resources.py"
        script.parent.mkdir(parents=True)
        script.write_text('''
import os
from pathlib import Path

assert Path.cwd() == Path(os.environ["OCTELIUM_TEST_DIR"])
print("kind: Config\\nmetadata: {name: example}\\ndata: {key: synthetic}")
''')
        self.fake_command("uv", '''
import subprocess
import sys
from pathlib import Path

assert sys.argv[1] == "run"
assert Path(sys.argv[2]).is_absolute()
sys.exit(subprocess.call([sys.executable, *sys.argv[2:]]))
''')
        text = f"octelium_skill_dir='{skill}'\n" + self.recipe("octelium-management", "apply-workflow.md", 2)
        result = self.run_recipe(text.replace("<DOMAIN>", "example.com"))
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.directory / result.stdout.strip()
        self.assertEqual(path.parent, self.directory)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn("kind: Config", path.read_text())

    def recovery_recipe(self) -> str:
        text = self.recipe("octelium-cluster-ops", "recovery-and-uninstall.md", 0)
        return text.replace("/secure/path/", str(self.directory) + "/").replace("<DOMAIN>", "example.com")

    def test_recovery_uses_environment_and_removes_temporary_token(self) -> None:
        self.fake_command("kubectl", '''
import base64
print(base64.b64encode(b"synthetic-initial-token").decode())
''')
        self.fake_command("octelium", '''
import os
import stat
import sys
from pathlib import Path

directory = Path(os.environ["OCTELIUM_TEST_DIR"])
files = list(directory.glob("init-token.*"))
assert len(files) == 1
assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
assert os.environ["OCTELIUM_AUTH_TOKEN"] == "synthetic-initial-token"
assert "synthetic-initial-token" not in " ".join(sys.argv)
(directory / "login-called").touch()
''')
        result = self.run_recipe(self.recovery_recipe())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertTrue((self.directory / "login-called").exists())
        self.assertEqual(list(self.directory.glob("init-token.*")), [])

    def test_recovery_producer_failure_does_not_login(self) -> None:
        self.fake_command("kubectl", "import sys\nsys.exit(1)\n")
        self.fake_command("octelium", 'from pathlib import Path\nPath("login-called").touch()\n')
        result = self.run_recipe(self.recovery_recipe())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.directory / "login-called").exists())
        self.assertEqual(list(self.directory.glob("init-token.*")), [])

    def test_kubernetes_init_suppresses_token_and_saves_privately(self) -> None:
        path = ROOT / "skills" / "octelium-kubernetes-install" / "SKILL.md"
        recipe = re.findall(r"```bash\n(.*?)\n\s*```", path.read_text(), re.S)[0]
        recipe = recipe.replace("<DOMAIN>", "example.com").replace("<path>", "kubeconfig").replace("<ctx>", "context")
        recipe = recipe.replace("[--version <v>]", "--version v0.43.0")
        self.fake_command("octops", '''
import os
import stat
from pathlib import Path

assert os.environ["OCTELIUM_SKIP_MESSAGES"] == "true"
path = Path(os.environ["OCTELIUM_AUTH_TOKEN_SAVE_PATH"])
assert stat.S_IMODE(path.stat().st_mode) == 0o600
path.write_text("synthetic-initial-token")
''')
        result = self.run_recipe(recipe)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("synthetic-initial-token", result.stdout)
        token_file = self.directory / result.stdout.strip()
        self.assertEqual(stat.S_IMODE(token_file.stat().st_mode), 0o600)
        self.assertEqual(token_file.read_text(), "synthetic-initial-token")

    def test_historical_login_lines_are_filtered(self) -> None:
        path = self.directory / "installer.log"
        path.write_text("starting init\noctelium login --domain example.com --auth-token synthetic-initial-token\ninstallation complete\n")
        recipe = f"sed '/--auth-token/d' '{path}' | tail -n 200"
        result = self.run_recipe(recipe)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "starting init\ninstallation complete\n")


if __name__ == "__main__":
    unittest.main()
