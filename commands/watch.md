---
description: Watch global Claude skills and commands and synchronize configured destinations
argument-hint: "[--interval seconds] [--install-launch-agent]"
allowed-tools:
  - "Bash(python3:*)"
  - Read
---

Before running, check for a pm-multimodels update:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" update-check`

- If it prints `UPGRADE_AVAILABLE`, read `${CLAUDE_PLUGIN_ROOT}/skills/upgrade/SKILL.md` and follow its inline upgrade flow before continuing.
- If it prints `JUST_UPGRADED <from> <to>`, print "Running pm-multimodels v{to} (just updated!)" and continue.
- If it prints nothing, continue normally.

Run:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" watch $ARGUMENTS`

Installing a launch agent changes user-level configuration. Ask for explicit approval before using `--install-launch-agent`.
