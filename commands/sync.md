---
description: Synchronize configured repositories and global Claude skills and commands
argument-hint: "[repository-path] [--global] [--apply]"
allowed-tools:
  - "Bash(python3:*)"
  - Read
---

Run:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" sync $ARGUMENTS`

Use dry-run mode unless the user explicitly requests applying changes. Stop and surface conflicts; do not overwrite unmanaged or modified destinations.
