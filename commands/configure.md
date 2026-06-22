---
description: Configure a repository to reuse Claude guidance, skills, and commands in Codex and Cursor
argument-hint: "<repository-path> [--mode symlink|copy] [--include-global] [--adopt-agents]"
allowed-tools:
  - "Bash(python3:*)"
  - Read
---

Before running, check for a pm-multimodels update:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" update-check`

- If it prints `UPGRADE_AVAILABLE`, read `${CLAUDE_PLUGIN_ROOT}/skills/upgrade/SKILL.md` and follow its inline upgrade flow before continuing.
- If it prints `JUST_UPGRADED <from> <to>`, print "Running pm-multimodels v{to} (just updated!)" and continue.
- If it prints nothing, continue normally.

Configure the target repository with the pm-multimodels engine.

1. Run a dry run first:
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" configure $ARGUMENTS`
2. Review every conflict and question with the user. Never choose replacement behavior silently.
3. If the user approves the reported changes, rerun the same command with `--apply`.
4. Report generated destinations, symlinks, ignored paths, and unresolved conflicts.

Treat `CLAUDE.md`, `.claude/skills/`, and `.claude/commands/` as canonical sources.
