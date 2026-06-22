# pm-multimodels

`pm-multimodels` is a Claude Code plugin that treats Claude configuration as canonical and translates it for Codex and Cursor.

It synchronizes:

- Project guidance from `CLAUDE.md`
- Global and project Claude skills
- Global and project Claude commands
- Codex `AGENTS.md`, skills, and command skills/prompts
- Cursor compatibility rules, skills, and commands

MCP synchronization is intentionally deferred.

## Requirements

- macOS or Linux
- Python 3.11 or newer
- Claude Code
- Codex and Cursor when testing their generated configuration

The sync engine uses only the Python standard library. No package installation is required.

## Install

Clone the repository:

```bash
git clone https://github.com/mbjornson/pm-multimodel.git ~/Projects/pm-multimodels
cd ~/Projects/pm-multimodels
```

Validate the plugin:

```bash
claude plugin validate .
```

Register this checkout as a local Claude marketplace:

```bash
claude plugin marketplace add "$PWD"
```

Install the plugin persistently:

```bash
claude plugin install pm-multimodels@pm-multimodels --scope user
```

Restart Claude Code, then verify the installation:

```bash
claude plugin list
claude plugin details pm-multimodels@pm-multimodels
```

The plugin should appear as enabled at user scope.

### Temporary Development Loading

To test the current checkout without installing it:

```bash
claude --plugin-dir "$PWD"
```

`--plugin-dir` only loads the plugin for that Claude process. It does not install the plugin or add it to `claude plugin list`.

Keep the repository in a stable location after registering the local marketplace. Claude uses that marketplace source when installing or updating the plugin.

### Update Or Remove

After changing the plugin, update the local marketplace and installed plugin:

```bash
claude plugin marketplace update pm-multimodels
claude plugin update pm-multimodels@pm-multimodels
```

Uninstall the plugin and remove its marketplace:

```bash
claude plugin uninstall pm-multimodels@pm-multimodels
claude plugin marketplace remove pm-multimodels
```

## Self-Upgrade

pm-multimodels checks for its own updates when you run any of its commands.
Detection is git-based: it compares your checkout against `origin/main`.

When an update is available, Claude prompts you to install it. Installing runs:

```bash
./scripts/pm-multimodels upgrade
```

which pulls the new version, reinstalls the Claude plugin, and re-syncs the
Codex and Cursor adapters so all three tools move together. Codex and Cursor
surface the same notice through the self-update block written into each
configured repository's `AGENTS.md` and Cursor rule.

If your plugin checkout has local changes, upgrade stashes both tracked and
untracked files before resetting to `origin/main`. If those changes cannot be
stashed cleanly, the upgrade stops before changing the checkout. After a
successful upgrade with stashed changes, run `git stash pop` in the plugin
directory when you are ready to reapply them.

### Update Configuration

Config lives in `~/.pm-multimodels/config`:

```bash
./scripts/pm-multimodels config set auto_upgrade true    # install updates without asking
./scripts/pm-multimodels config set update_check false   # stop checking for updates
```

Declining an update snoozes the reminder with escalating backoff
(24h, then 48h, then weekly).

The engine can also be used without loading the Claude plugin:

```bash
./scripts/pm-multimodels --help
```

## Configure A Repository

The target repository must contain a root `CLAUDE.md`.

Start with a dry run:

```text
/pm-multimodels:configure /path/to/repository
```

Or use the CLI:

```bash
./scripts/pm-multimodels configure /path/to/repository
```

Review the proposed operations and conflicts. Nothing is written during a dry run.

Apply an approved plan:

```bash
./scripts/pm-multimodels configure /path/to/repository --apply
```

By default, generated project skills are exposed through symlinks. To create regular files that can be committed:

```bash
./scripts/pm-multimodels configure /path/to/repository \
  --mode copy \
  --apply
```

### Existing `AGENTS.md`

An existing hand-authored `AGENTS.md` is treated as a conflict. After reviewing and approving replacement, run:

```bash
./scripts/pm-multimodels configure /path/to/repository \
  --adopt-agents \
  --apply
```

The original file is preserved at:

```text
.pm-multimodels/backups/AGENTS.md.bak
```

### Cursor Ignore Rules

If `.gitignore` excludes `.cursor/*`, the dry run reports that generated Cursor skills and commands will remain untracked. To add the required exceptions:

```bash
./scripts/pm-multimodels configure /path/to/repository \
  --update-gitignore \
  --apply
```

The user decides whether generated project artifacts belong in Git.

## Generated Project Files

Depending on the selected mode and available Claude sources, configuration creates:

```text
AGENTS.md
.agents/skills/
.cursor/rules/999-pm-multimodels.mdc
.cursor/skills/
.cursor/commands/
.pm-multimodels.json
.pm-multimodels/
```

`CLAUDE.md`, `.claude/skills/`, and `.claude/commands/` are never modified.

## Global Skills And Commands

Synchronize global Claude sources:

```text
/pm-multimodels:sync --global
```

Or:

```bash
./scripts/pm-multimodels sync --global --apply
```

Sources:

```text
~/.claude/skills/
~/.claude/commands/
```

Destinations include:

```text
~/.agents/skills/
~/.cursor/skills/
~/.cursor/commands/
~/.codex/prompts/
```

Global destinations are symlinked to platform-specific generated adapters under `~/.pm-multimodels/generated/`. Raw Claude skills are not linked directly into Codex or Cursor.

To configure a repository and include global synchronization in the same workflow:

```bash
./scripts/pm-multimodels configure /path/to/repository \
  --include-global \
  --apply
```

## Synchronize Changes

Synchronize a previously configured repository:

```text
/pm-multimodels:sync /path/to/repository
```

Or:

```bash
./scripts/pm-multimodels sync /path/to/repository --apply
```

The repository’s `.pm-multimodels.json` records its selected mode and global synchronization preference.

## Watch For Changes

Run the watcher in the foreground:

```text
/pm-multimodels:watch
```

Or:

```bash
./scripts/pm-multimodels watch
```

The watcher polls these sources every two seconds:

- `~/.claude/skills/`
- `~/.claude/commands/`
- Registered repositories’ `CLAUDE.md`
- Registered repositories’ `.claude/skills/`
- Registered repositories’ `.claude/commands/`

When a source changes, it regenerates global adapters and synchronizes registered repositories. Conflicts are logged and never overwritten.

Change the polling interval:

```bash
./scripts/pm-multimodels watch --interval 5
```

### Install The macOS Watcher

Install and start a persistent LaunchAgent:

```text
/pm-multimodels:watch --install-launch-agent
```

Or:

```bash
./scripts/pm-multimodels watch --install-launch-agent
```

This creates:

```text
~/Library/LaunchAgents/com.pm-multimodels.watch.plist
~/.pm-multimodels/logs/watch.stdout.log
~/.pm-multimodels/logs/watch.stderr.log
```

Remove the LaunchAgent:

```bash
launchctl bootout "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.pm-multimodels.watch.plist"
rm "$HOME/Library/LaunchAgents/com.pm-multimodels.watch.plist"
```

Persistent watcher installation is currently macOS-only.

## Diagnose Problems

Inspect global configuration:

```text
/pm-multimodels:doctor
```

Inspect a target repository:

```bash
./scripts/pm-multimodels doctor /path/to/repository
```

The doctor reports missing canonical sources, unconfigured repositories, and broken global skill symlinks.

## Conflict Policy

Synchronization stops with a nonzero exit status when:

- A destination exists but is not managed by `pm-multimodels`
- A managed destination was edited after generation
- Multiple Claude sources normalize to the same destination name
- Repository configuration is invalid
- `CLAUDE.md` is missing

Resolve the conflict with the user, then rerun the dry run. The tool never silently overwrites conflicts.

## Development

Run the tests:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m unittest discover -s tests -v
```

Validate the embedded skill:

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py \
  skills/configure-multimodel
```

Validate the Claude plugin:

```bash
claude plugin validate .
```
