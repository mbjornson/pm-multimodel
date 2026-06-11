---
name: configure-multimodel
description: Configure and synchronize repositories so Codex and Cursor reuse canonical Claude Code guidance, global and project skills, and commands. Use when setting up a target repository, translating Claude-specific tools, diagnosing configuration drift, resolving generated-file conflicts, or installing the global watcher.
---

# Configure Multimodel

Use the deterministic engine instead of manually copying or rewriting configuration.

## Configure A Repository

1. Identify the repository root and confirm `CLAUDE.md` is the canonical project file.
2. Run:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" configure <repo>
   ```

3. Review the dry-run report with the user.
4. Stop on every unmanaged destination or modified generated artifact.
5. Ask the user to choose `symlink` or `copy` for repository artifacts.
6. Ask separately before changing `.gitignore` or replacing an existing `AGENTS.md`.
7. Apply only after approval by adding `--apply`.

## Synchronize Global Sources

Use `sync --global` to translate `~/.claude/skills` and `~/.claude/commands` into the managed cache, then expose them to Codex and Cursor with symlinks.

Never symlink raw Claude skills directly into another platform. Generate a platform adapter first, then symlink the adapter directory.

## Watch For Changes

Use `watch` for a foreground watcher. On macOS, use `watch --install-launch-agent` only after explicit approval.

## Conflict Policy

- Treat files containing the pm-multimodels ownership marker as managed.
- Treat matching managed symlinks as safe to refresh.
- Treat every other existing destination as a conflict.
- Never overwrite, delete, or replace a conflict automatically.
- Return a nonzero exit status when conflicts exist.

## Translation Contract

Read [references/translation-contract.md](references/translation-contract.md) when reviewing adapters or adding mappings.
