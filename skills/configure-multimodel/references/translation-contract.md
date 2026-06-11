# Translation Contract

## Canonical Sources

- Project guidance: `CLAUDE.md`
- Project skills: `.claude/skills/*/SKILL.md`
- Project commands: `.claude/commands/*.md`
- Global skills: `~/.claude/skills/*/SKILL.md`
- Global commands: `~/.claude/commands/*.md`

## Codex

- Generate a small `AGENTS.md` adapter that requires reading `CLAUDE.md`.
- Generate skills under `.agents/skills`.
- Expose global skills under `~/.agents/skills`.
- Convert commands into explicit-invocation skills and legacy custom prompts.
- Map Claude tool names to capabilities, not pinned model names.

## Cursor

- Cursor reads root `CLAUDE.md`; generate only a tool-mapping rule.
- Generate project skills under `.cursor/skills`.
- Expose global skills under `~/.cursor/skills`.
- Generate commands under `.cursor/commands`.

## Safety

- Preserve canonical sources.
- Mark every generated regular file.
- Record source and output hashes in a manifest.
- Stop on unmanaged destinations and modified managed outputs.
- Do not silently modify ignore rules.
