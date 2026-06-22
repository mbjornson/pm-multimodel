---
name: upgrade
description: Notify about and install pm-multimodels plugin updates across Claude, Codex, and Cursor. Use when an update check prints UPGRADE_AVAILABLE, or when the user asks to upgrade or update the pm-multimodels plugin.
allowed-tools:
  - "Bash(python3:*)"
  - Read
  - Write
  - AskUserQuestion
---

# Upgrade pm-multimodels

Run pm-multimodels' update check and, if an update exists, install it. The CLI
lives at `${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels`.

## Inline upgrade flow

Referenced by every pm-multimodels command preamble when it sees
`UPGRADE_AVAILABLE <old> <new>`.

### Step 1: Auto-upgrade or ask

Check the auto-upgrade flag:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" config get auto_upgrade`

**If it prints `true`:** log "Auto-upgrading pm-multimodels v{old} -> v{new}..."
and go to Step 2.

**Otherwise** use AskUserQuestion:
- Question: "pm-multimodels **v{new}** is available (you're on v{old}). Upgrade now?"
- Options: "Upgrade now" / "Always keep me up to date" / "Not now" / "Never ask again".

- **Upgrade now** -> Step 2.
- **Always keep me up to date** ->
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" config set auto_upgrade true`,
  tell the user future updates install automatically, then Step 2.
- **Not now** ->
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" snooze {new}`,
  relay the printed "next reminder" window, then continue the original task. Do
  not mention the update again this session.
- **Never ask again** ->
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" config set update_check false`,
  tell the user how to re-enable
  (`... config set update_check true`), then continue the original task.

### Step 2: Install

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" upgrade`

The command pulls the new version, reinstalls the Claude plugin (best-effort),
re-syncs Codex and Cursor, and prints the version transition plus a one-line-per
commit changelog. Relay any notes it prints (stashed changes, sync conflicts).

### Step 3: Show what's new

From the command's `Changes:` output, summarize 5-7 user-facing bullets grouped
by theme. Skip pure-internal refactors. Then continue with whatever the user was
doing.

## Standalone usage

When invoked directly as `/pm-multimodels:upgrade`, force a fresh check first:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" update-check --force`

If it prints `UPGRADE_AVAILABLE`, follow the inline flow. If it prints nothing,
tell the user they are already on the latest version.
