import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pm_multimodels.engine import SyncEngine


def write_skill(root: Path, name: str = "demo") -> None:
    skill = root / ".claude/skills" / name / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(
        f"""---
name: {name}
description: Run the {name} workflow
---

Use Read and Bash.
"""
    )


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.user_home = root / "user"
        self.repo = root / "repo"
        self.state = root / "state"
        self.user_home.mkdir()
        self.repo.mkdir()
        self.repo.joinpath("CLAUDE.md").write_text("# Canonical\n\nUse the Read tool.\n")
        self.engine = SyncEngine(home=self.state, user_home=self.user_home)

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_agents_file_is_a_conflict(self):
        self.repo.joinpath("AGENTS.md").write_text("# Hand authored\n")

        report = self.engine.configure(self.repo)

        self.assertFalse(report.ok)
        self.assertIn("Unmanaged destination exists", report.conflicts[0])
        self.assertEqual("# Hand authored\n", self.repo.joinpath("AGENTS.md").read_text())

    def test_approved_agents_adoption_preserves_backup(self):
        self.repo.joinpath("AGENTS.md").write_text("# Hand authored\n")

        report = self.engine.configure(
            self.repo, adopt_agents=True, apply=True
        )

        self.assertTrue(report.ok, report.conflicts)
        backup = self.repo / ".pm-multimodels/backups/AGENTS.md.bak"
        self.assertEqual("# Hand authored\n", backup.read_text())

    def test_configure_generates_adapters_and_symlinks(self):
        self.repo.joinpath(".gitignore").write_text("/.cursor/*\n!/.cursor/rules/\n")
        write_skill(self.repo)
        command = self.repo / ".claude/commands/review.md"
        command.parent.mkdir(parents=True)
        command.write_text("---\ndescription: Review code\n---\n\nUse Read.\n")

        report = self.engine.configure(
            self.repo, update_gitignore=True, apply=True
        )

        self.assertTrue(report.ok, report.conflicts)
        self.assertIn("read `CLAUDE.md` in full", self.repo.joinpath("AGENTS.md").read_text())
        self.assertTrue(self.repo.joinpath(".agents/skills/demo").is_symlink())
        self.assertTrue(self.repo.joinpath(".cursor/skills/demo").is_symlink())
        self.assertTrue(
            self.repo.joinpath(".agents/skills/claude-command-review").is_symlink()
        )
        self.assertTrue(self.repo.joinpath(".cursor/commands/review.md").is_file())
        self.assertIn("!/.cursor/skills/", self.repo.joinpath(".gitignore").read_text())
        config = json.loads(self.repo.joinpath(".pm-multimodels.json").read_text())
        self.assertEqual("pm-multimodels", config["generated_by"])

    def test_modified_managed_file_stops_sync(self):
        first = self.engine.configure(self.repo, apply=True)
        self.assertTrue(first.ok)
        self.repo.joinpath("AGENTS.md").write_text(
            self.repo.joinpath("AGENTS.md").read_text() + "\nmanual edit\n"
        )

        report = self.engine.sync_repo(self.repo)

        self.assertFalse(report.ok)
        self.assertTrue(
            any("Managed destination was modified" in item for item in report.conflicts)
        )

    def test_copy_mode_detects_modified_resource(self):
        write_skill(self.repo)
        reference = self.repo / ".claude/skills/demo/reference.md"
        reference.write_text("canonical\n")
        first = self.engine.configure(self.repo, mode="copy", apply=True)
        self.assertTrue(first.ok, first.conflicts)
        generated = self.repo / ".agents/skills/demo/reference.md"
        generated.write_text("manual edit\n")

        report = self.engine.sync_repo(self.repo)

        self.assertFalse(report.ok)
        self.assertTrue(
            any("Managed destination was modified" in item for item in report.conflicts)
        )

    def test_canonical_change_regenerates_cleanly(self):
        first = self.engine.configure(self.repo, apply=True)
        self.assertTrue(first.ok)
        self.repo.joinpath("CLAUDE.md").write_text("# Canonical changed\n")

        report = self.engine.sync_repo(self.repo, apply=True)

        self.assertTrue(report.ok, report.conflicts)
        self.assertIn("canonical-source", self.repo.joinpath("AGENTS.md").read_text())

    def test_global_sync_uses_generated_cache_and_symlinks(self):
        global_skill = self.user_home / ".claude/skills/global-demo/SKILL.md"
        global_skill.parent.mkdir(parents=True)
        global_skill.write_text(
            "---\nname: global-demo\ndescription: Global demo\n---\n\nUse Read.\n"
        )

        report = self.engine.sync_global(apply=True)

        self.assertTrue(report.ok, report.conflicts)
        codex = self.user_home / ".agents/skills/global-demo"
        cursor = self.user_home / ".cursor/skills/global-demo"
        self.assertTrue(codex.is_symlink())
        self.assertTrue(cursor.is_symlink())
        self.assertNotEqual(global_skill.parent.resolve(), codex.resolve())

    def test_fingerprint_changes_with_registered_project_sources(self):
        first = self.engine.configure(self.repo, apply=True)
        self.assertTrue(first.ok)
        before = self.engine.source_fingerprint()
        self.repo.joinpath("CLAUDE.md").write_text("# Changed\n")

        after = self.engine.source_fingerprint()

        self.assertNotEqual(before, after)

    def test_nested_global_skill_is_discovered(self):
        skill = self.user_home / ".claude/skills/group/nested/SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text(
            "---\nname: nested-demo\ndescription: Nested demo\n---\n\nUse Read.\n"
        )

        report = self.engine.sync_global(apply=True)

        self.assertTrue(report.ok, report.conflicts)
        self.assertTrue(
            self.user_home.joinpath(".agents/skills/nested-demo").is_symlink()
        )

    def test_duplicate_skill_names_are_a_conflict(self):
        first = self.user_home / ".claude/skills/one/SKILL.md"
        second = self.user_home / ".claude/skills/two/SKILL.md"
        first.parent.mkdir(parents=True)
        second.parent.mkdir(parents=True)
        content = "---\nname: duplicate\ndescription: Duplicate\n---\n"
        first.write_text(content)
        second.write_text(content)

        report = self.engine.sync_global()

        self.assertFalse(report.ok)
        self.assertTrue(any("Multiple sources map" in item for item in report.conflicts))


if __name__ == "__main__":
    unittest.main()
