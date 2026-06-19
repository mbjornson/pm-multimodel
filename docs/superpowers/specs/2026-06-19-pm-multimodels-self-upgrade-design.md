# pm-multimodels Self-Upgrade — Design

**Date:** 2026-06-19
**Status:** Approved, pending implementation plan

## Problem

When a new version of the `pm-multimodels` plugin is published, the user has no
way to find out except by manually running `claude plugin update`. The feature
adds proactive update notification and one-step installation across all three
tools the plugin serves: Claude, Codex, and Cursor.

The behavior is modeled on the `gstack` plugin's upgrade flow, adapted to
pm-multimodels' distribution (a git repo that is also a Claude marketplace
plugin and a generator of Codex/Cursor adapters).

## Decisions (locked during brainstorming)

1. **Update source: git-based.** Detect with `git fetch` against the GitHub
   remote (`git@github.com:mbjornson/pm-multimodel.git`); install with a git
   update of the checkout, then reinstall the Claude plugin and re-sync the
   Codex/Cursor adapters. One mechanism that works the same everywhere.
2. **Check trigger: on-demand per tool, gstack-style.** No persistent daemon
   and no SessionStart hook. The check runs when a pm-multimodels skill/command
   is invoked, rate-limited by a timestamp cache. Accepted limitation: Codex and
   Cursor only notice when the user invokes pm-multimodels work (they run no
   Claude session hooks).
3. **Upgrade UX: full gstack parity.** 4-option prompt, escalating snooze
   backoff, `auto_upgrade` + `update_check` config flags.
4. **Claude trigger: skill-preamble only.** No `hooks.json`. Smallest footprint.

## Key Insights

- **Commands are thin shells.** Every command is
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" <cmd> $ARGUMENTS`.
  New behavior is new CLI subcommands plus skill prose, not new plumbing.
- **The plugin's own skills are not synced.** The engine syncs the *user's*
  Claude config (`CLAUDE.md`, `~/.claude/...`, project `.claude/...`) into
  Codex/Cursor. Plugin internals never reach those tools. Therefore Codex and
  Cursor can only learn about a pm-multimodels update through the **adapters the
  engine generates** (`AGENTS.md`, `.cursor/rules/999-pm-multimodels.mdc`). The
  notification is itself a cross-model sync problem — which this plugin already
  has machinery for.
- **Tool-name translation already exists.** The translation contract maps Claude
  tool names to capabilities, so an `AskUserQuestion` in the upgrade skill
  survives translation to Codex/Cursor as a plain "ask the user."

## Architecture

Six components.

### 1. `update-check` CLI subcommand

New module `src/pm_multimodels/updater.py`, wired into `cli.py` as the
`update-check` subcommand.

- Runs a rate-limited `git fetch` on the plugin's own checkout, located via
  `CLAUDE_PLUGIN_ROOT` (falling back to the script's resolved repo root).
- "Update available" iff `origin/main` is strictly ahead of local `HEAD`
  (`git rev-list HEAD..origin/main --count > 0`).
- Prints exactly one of:
  - `UPGRADE_AVAILABLE <old> <new>`
  - `JUST_UPGRADED <from> <to>` (when the `just-upgraded-from` marker is present;
    consumed and cleared after printing)
  - nothing (up to date, or the check is suppressed)
- Version strings are **displayed** from `.claude-plugin/plugin.json`: local
  `version` vs the remote value from
  `git show origin/main:.claude-plugin/plugin.json`. Git ahead/behind decides
  *whether* an update exists; plugin.json decides *what to show*.
- Suppressed when `update_check=false`, when an active snooze covers the current
  remote version, or when the timestamp cache is fresh. `--force` bypasses the
  cache (but not `update_check=false`).
- Offline / `git fetch` failure is a **silent no-op** that exits 0. The check
  must never block real work.

### 2. State and config directory `~/.pm-multimodels/`

Reuses the existing plugin home directory (already used for `generated/`,
`logs/`).

- `config` — `auto_upgrade` and `update_check` flags. Accessed via a `config
  get <key>` / `config set <key> <value>` subcommand, mirroring `gstack-config`.
  Format: simple `key=value` lines (no YAML dependency; stdlib only, consistent
  with the engine's stdlib-only constraint).
- `last-update-check` — unix timestamp of the last network check (rate-limit
  gate).
- `update-snoozed` — `<version> <level> <timestamp>`. Snooze applies only while
  `<version>` equals the current remote version; a newer remote version resets
  the snooze.
- `just-upgraded-from` — previous version string, written by `upgrade`, consumed
  by `update-check` to emit `JUST_UPGRADED`.

### 3. `upgrade` CLI subcommand

The non-interactive installer. The interactive prompting lives in the skill
(component 4); this subcommand just performs the work so it can be called from
any tool.

Sequence:
1. Record current `HEAD` and plugin.json version (for rollback + marker).
2. `git fetch` + `git reset --hard origin/main` in the checkout. If the working
   tree is dirty, `git stash` first and warn the user to `git stash pop`.
3. Reinstall the Claude plugin: `claude plugin marketplace update pm-multimodels`
   then `claude plugin update pm-multimodels@pm-multimodels`.
4. **Re-run sync** so Codex/Cursor adapters refresh: `sync --global` plus
   `sync <repo>` for each registered repo. An upgrade that did not refresh the
   other two tools would be half-done.
5. Write `just-upgraded-from`; clear `last-update-check` and `update-snoozed`.

On failure at any step: `git reset --hard` back to the saved old `HEAD` and warn
the user that the previous version was restored and to retry
`/pm-multimodels:upgrade`.

### 4. `upgrade` skill + command (Claude)

- `skills/upgrade/SKILL.md` — ports gstack's "Inline upgrade flow":
  - Read `auto_upgrade`. If true: log "Auto-upgrading v{old} → v{new}…" and run
    `pm-multimodels upgrade` directly.
  - Else `AskUserQuestion` with four options: **Upgrade now** / **Always keep me
    up to date** / **Not now** / **Never ask again**.
    - *Upgrade now* → run `pm-multimodels upgrade`.
    - *Always* → `config set auto_upgrade true`, then upgrade.
    - *Not now* → run `pm-multimodels snooze` (CLI computes the escalating
      backoff: level 1 = 24h, 2 = 48h, 3+ = 1 week, and prints the resulting
      window), relay the next-reminder window to the user, continue the original
      task. Escalation lives in the CLI, not inline skill bash, so Codex/Cursor
      get the same behavior without re-translating the logic.
    - *Never* → `config set update_check false`, tell the user how to re-enable,
      continue.
  - After a successful upgrade, show **"What's new"**: summarize the git log
    between old and new versions as 5–7 themed bullets.
- `commands/upgrade.md` — thin shell exposing `/pm-multimodels:upgrade`.
  Standalone invocation forces a fresh check (`update-check --force`) and then
  follows the inline flow; if already current, says so.

### 5. Preambles on existing commands

`configure`, `sync`, `doctor`, `watch` each gain a short preamble block:

> Run `update-check`. If output is `UPGRADE_AVAILABLE`, read the upgrade skill
> and follow its inline flow before continuing. If output is `JUST_UPGRADED`,
> print a one-line confirmation.

To avoid drift, the snippet is authored once (e.g.
`skills/upgrade/references/preamble.md`) and referenced from each command rather
than copy-pasted.

### 6. Cross-tool reach via generated adapters

The engine, when generating the Codex `AGENTS.md` adapter and the Cursor rule
`.cursor/rules/999-pm-multimodels.mdc`, embeds a self-update block:

> Before doing pm-multimodels work, run
> `python3 <plugin>/scripts/pm-multimodels update-check`. If it prints
> `UPGRADE_AVAILABLE`, tell the user an update is available and offer to run
> `python3 <plugin>/scripts/pm-multimodels upgrade` for them.

This is the only path by which Codex and Cursor surface the notice. No daemon,
no hook. `AskUserQuestion` in the Claude skill maps to a plain "ask the user" in
these tools per the existing translation contract.

## Error Handling

| Condition | Behavior |
| --- | --- |
| Offline / `git fetch` fails | Silent no-op, exit 0. Never block work. |
| Cache fresh | Skip network, print nothing. |
| `update_check=false` | Skip entirely (even with a pending update). |
| Active snooze for current remote version | Skip until snooze expires. |
| Dirty working tree on upgrade | `git stash`, proceed, warn to `stash pop`. |
| Any upgrade step fails | `git reset --hard` to saved old HEAD, warn, advise retry. |

## Testing

- **Unit (`updater.py`)** with git/`subprocess` and the clock stubbed:
  - version comparison (ahead/behind/equal)
  - snooze escalation (24h → 48h → 1wk; reset on new remote version)
  - cache rate-limit gating (`--force` bypass)
  - config read/write round-trip and defaults
  - `update_check=false` suppression
  - `JUST_UPGRADED` marker emit-and-clear
- **Engine** test asserting generated `AGENTS.md` and the Cursor rule contain the
  update-check instruction (substring check), under both `copy` and `symlink`
  modes.
- Follows the repo's existing harness:
  `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests`.

## Out of Scope (YAGNI)

- Persistent watcher/daemon-driven checks (explicitly rejected).
- SessionStart hook (explicitly rejected).
- MCP synchronization (already deferred project-wide).
- Migration scripts between versions (gstack has them; not needed until
  pm-multimodels has state that survives upgrades and needs fixing).

## Files Touched (anticipated)

- `src/pm_multimodels/updater.py` (new)
- `src/pm_multimodels/cli.py` (wire `update-check`, `upgrade`, `config`, `snooze`)
- `src/pm_multimodels/engine.py` (emit self-update block into adapters)
- `skills/upgrade/SKILL.md` (new), `skills/upgrade/references/preamble.md` (new)
- `commands/upgrade.md` (new)
- `commands/configure.md`, `commands/sync.md`, `commands/doctor.md`,
  `commands/watch.md` (add preamble reference)
- `tests/test_updater.py` (new), `tests/test_engine.py` (adapter assertions)
- `README.md` (document the upgrade flow + config flags)
