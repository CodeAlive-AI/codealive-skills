# Plugin Bridge

Keep an AI agent's skills directory in sync with the Claude Code `codealive`
plugin's versioned cache. The bridge lets agents like Codex CLI, Gemini CLI,
Cursor, or Windsurf consume the same skill files the Claude Code plugin
installs, and updates the link automatically on `claude plugin update`.

## Why

Claude Code stores plugins under a versioned cache:
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. Every call to
`claude plugin update` writes a new versioned directory and leaves the old one
behind. Agents other than Claude Code don't read from that cache — they look
for skills in their own directories (`~/.codex/skills/`, `~/.gemini/skills/`,
etc.).

A symlink from the agent's skills directory into the cache lets them share the
plugin's skill with zero duplication. The trade-off: that symlink breaks every
time the plugin version changes. `plugin-bridge` rewrites the symlink to point
at the newest versioned directory whenever the cache changes on disk.

## Files

| File | Purpose |
|------|---------|
| `update-symlink.sh` | Scans the plugin cache and refreshes the agent symlink if the target has changed |
| `com.codealive.plugin-bridge.plist.template` | `launchd` agent template with placeholders |
| `install-macos.sh` | Renders the plist, writes it to `~/Library/LaunchAgents`, and bootstraps the agent |
| `uninstall-macos.sh` | Removes the `launchd` agent; leaves existing symlinks untouched |

## Install (macOS)

```bash
./install-macos.sh
```

Verify the symlink and the agent:

```bash
ls -la ~/.codex/skills/codealive-context-engine
launchctl print "gui/$(id -u)/com.codealive.plugin-bridge" | head
cat /tmp/codealive-plugin-bridge.log
```

Run `claude plugin update codealive@codealive-marketplace`, then re-check the
symlink — it should now point at the new version's directory.

## Configure

All paths are environment-variable driven with defaults suitable for Codex CLI.
Export the variables before running `install-macos.sh` to target a different
agent.

| Variable | Default |
|----------|---------|
| `CODEALIVE_PLUGIN_CACHE` | `~/.claude/plugins/cache/codealive-marketplace/codealive` |
| `CODEALIVE_PLUGIN_SUBPATH` | `skills/codealive-context-engine` |
| `CODEALIVE_AGENT_LINK` | `~/.codex/skills/codealive-context-engine` |

Example for Gemini CLI:

```bash
CODEALIVE_AGENT_LINK=~/.gemini/skills/codealive-context-engine ./install-macos.sh
```

Note: environment variables are read by `update-symlink.sh` at runtime.
`launchd` launches it via `/bin/bash` without inheriting your shell, so the
overrides must be either baked into the script, exported in `~/.zshenv`, or
injected through an `EnvironmentVariables` key in the plist.

## Uninstall (macOS)

```bash
./uninstall-macos.sh
```

## Linux

A `systemd --user` path unit gives the equivalent behaviour. Create two files:

`~/.config/systemd/user/codealive-plugin-bridge.path`:

```ini
[Unit]
Description=Watch CodeAlive plugin cache

[Path]
PathModified=%h/.claude/plugins/cache/codealive-marketplace/codealive

[Install]
WantedBy=default.target
```

`~/.config/systemd/user/codealive-plugin-bridge.service`:

```ini
[Unit]
Description=Refresh CodeAlive plugin symlink

[Service]
Type=oneshot
ExecStart=/bin/bash %h/path/to/update-symlink.sh
```

Enable with `systemctl --user enable --now codealive-plugin-bridge.path`.

## Windows

No native file-watcher is shipped here. A Task Scheduler entry calling
`update-symlink.sh` via WSL bash or a PowerShell port on login and every
N minutes is a reasonable fallback.
