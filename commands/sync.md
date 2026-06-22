---
description: Synchronize configured repositories and global Claude skills and commands
argument-hint: "[repository-path] [--global] [--apply]"
allowed-tools:
  - "Bash(python3:*)"
  - Read
---

Before running, check for a pm-multimodels update:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" update-check`
If it prints `UPGRADE_AVAILABLE`, read `${CLAUDE_PLUGIN_ROOT}/skills/upgrade/SKILL.md` and follow its inline upgrade flow before continuing. If it prints `JUST_UPGRADED`, print a one-line confirmation.

Run:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" sync $ARGUMENTS`

Use dry-run mode unless the user explicitly requests applying changes. Stop and surface conflicts; do not overwrite unmanaged or modified destinations.
