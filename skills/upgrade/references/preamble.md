<!-- Canonical pm-multimodels update-check preamble.
     Keep the four command preambles (configure/sync/doctor/watch) in sync with this. -->

Before running, check for a pm-multimodels update:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pm-multimodels" update-check`

- If it prints `UPGRADE_AVAILABLE`, read `${CLAUDE_PLUGIN_ROOT}/skills/upgrade/SKILL.md` and follow its inline upgrade flow before continuing.
- If it prints `JUST_UPGRADED <from> <to>`, print "Running pm-multimodels v{to} (just updated!)" and continue.
- If it prints nothing, continue normally.
