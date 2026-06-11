---
description: Diagnose multimodel configuration, discovery, symlinks, and conflicts
argument-hint: "[repository-path]"
allowed-tools:
  - "Bash(python3:*)"
  - Read
---

Run:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" doctor $ARGUMENTS`

Explain failures in terms of canonical sources, generated cache entries, destination ownership, symlink health, and ignore rules.
