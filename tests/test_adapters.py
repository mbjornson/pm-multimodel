from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pm_multimodels.adapters import (
    MARKER,
    adapt_codex_prompt,
    adapt_command,
    adapt_skill,
    codex_agents_adapter,
    cursor_rule_adapter,
)


class AdapterTest(unittest.TestCase):
    def test_codex_skill_removes_claude_frontmatter_and_maps_paths(self):
        with TemporaryDirectory() as directory:
            skill = Path(directory) / "demo" / "SKILL.md"
            skill.parent.mkdir()
            skill.write_text(
                """---
name: demo
description: Demo workflow
allowed-tools:
  - Read
  - Bash
---

Read @$HOME/.claude/config and run /review $ARGUMENTS.
"""
            )

            name, output = adapt_skill(skill, "codex")

            self.assertEqual("demo", name)
            self.assertIn(MARKER, output)
            self.assertNotIn("allowed-tools:", output)
            self.assertIn("$HOME/.codex/config", output)
            self.assertIn("$review {{ARGS}}", output)

    def test_codex_command_becomes_namespaced_skill(self):
        with TemporaryDirectory() as directory:
            command = Path(directory) / "review.md"
            command.write_text(
                """---
description: Review a change
argument-hint: [path]
---

Review @$1.
"""
            )

            name, output = adapt_command(command, "codex")

            self.assertEqual("claude-command-review", name)
            self.assertIn("name: claude-command-review", output)
            self.assertIn("description: Review a change.", output)

    def test_codex_prompt_preserves_native_arguments(self):
        with TemporaryDirectory() as directory:
            command = Path(directory) / "review.md"
            command.write_text(
                """---
description: Review a change
argument-hint: "[path]"
---

Review $ARGUMENTS.
"""
            )

            output = adapt_codex_prompt(command)

            self.assertNotIn("name:", output)
            self.assertIn('argument-hint: "[path]"', output)
            self.assertIn("Review $ARGUMENTS.", output)


class SelfUpdateBlockTest(unittest.TestCase):
    def _claude(self, directory: str) -> Path:
        path = Path(directory) / "CLAUDE.md"
        path.write_text("# Canonical\n")
        return path

    def test_codex_adapter_includes_self_update_when_command_given(self):
        with TemporaryDirectory() as directory:
            claude = self._claude(directory)
            output = codex_agents_adapter(
                claude, update_command='python3 "/x/scripts/pm-multimodels"'
            )
            self.assertIn("update-check", output)
            self.assertIn("upgrade", output)

    def test_cursor_adapter_includes_self_update_when_command_given(self):
        with TemporaryDirectory() as directory:
            claude = self._claude(directory)
            output = cursor_rule_adapter(
                claude, update_command='python3 "/x/scripts/pm-multimodels"'
            )
            self.assertIn("update-check", output)

    def test_adapter_omits_block_without_command(self):
        with TemporaryDirectory() as directory:
            claude = self._claude(directory)
            self.assertNotIn("Self-Update", codex_agents_adapter(claude))


if __name__ == "__main__":
    unittest.main()
