---
description: Watch global Claude skills and commands and synchronize configured destinations
argument-hint: "[--interval seconds] [--install-launch-agent]"
allowed-tools:
  - "Bash(python3:*)"
  - Read
---

Run:

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" watch $ARGUMENTS`

Installing a launch agent changes user-level configuration. Ask for explicit approval before using `--install-launch-agent`.
