import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliTest(unittest.TestCase):
    def test_configure_dry_run_then_apply(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            repo = root / "repo"
            home.mkdir()
            repo.mkdir()
            repo.joinpath("CLAUDE.md").write_text("# Canonical\n")
            env = os.environ.copy()
            env["HOME"] = str(home)
            env["PM_MULTIMODELS_HOME"] = str(root / "state")
            env["PYTHONPATH"] = str(ROOT / "src")
            command = [
                sys.executable,
                str(ROOT / "scripts/pm-multimodels"),
                "configure",
                str(repo),
            ]

            dry_run = subprocess.run(
                command, env=env, text=True, capture_output=True, check=False
            )
            self.assertEqual(0, dry_run.returncode, dry_run.stderr)
            self.assertIn("PLAN write", dry_run.stdout)
            self.assertFalse(repo.joinpath("AGENTS.md").exists())

            applied = subprocess.run(
                [*command, "--apply"],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, applied.returncode, applied.stderr)
            self.assertTrue(repo.joinpath("AGENTS.md").is_file())
            self.assertIn("update-check", repo.joinpath("AGENTS.md").read_text())
            self.assertTrue(repo.joinpath(".pm-multimodels.json").is_file())


class UpdaterCliTest(unittest.TestCase):
    def _run(self, args, root, home):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["PM_MULTIMODELS_HOME"] = str(home)
        env["CLAUDE_PLUGIN_ROOT"] = str(root)
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts/pm-multimodels"), *args],
            env=env, text=True, capture_output=True, check=False,
        )

    def test_config_set_get_and_snooze(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            home = Path(directory) / "home"
            root.mkdir()
            home.mkdir()
            set_result = self._run(["config", "set", "auto_upgrade", "true"], root, home)
            self.assertEqual(0, set_result.returncode, set_result.stderr)
            get_result = self._run(["config", "get", "auto_upgrade"], root, home)
            self.assertEqual("true", get_result.stdout.strip())
            snooze_result = self._run(["snooze", "9.9.9"], root, home)
            self.assertEqual(0, snooze_result.returncode, snooze_result.stderr)
            self.assertIn("24h", snooze_result.stdout)

    def test_update_check_silent_when_disabled(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            home = Path(directory) / "home"
            root.mkdir()
            home.mkdir()
            self._run(["config", "set", "update_check", "false"], root, home)
            result = self._run(["update-check"], root, home)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
