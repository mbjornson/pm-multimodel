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
            self.assertTrue(repo.joinpath(".pm-multimodels.json").is_file())


if __name__ == "__main__":
    unittest.main()
