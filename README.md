# CodeAlive Skills

Agent skills and Claude Code plugin for [CodeAlive](https://app.codealive.ai) — install via [skills.sh](https://skills.sh/) or as a Claude Code plugin.

## Available Skills

| Skill | Description |
|-------|-------------|
| [codealive-context-engine](skills/codealive-context-engine/) | Semantic code search and AI-powered codebase Q&A across indexed repositories |

## Installation

> **Claude Code users:** the recommended installation method is [Option 2 (Plugin)](#option-2-claude-code-plugin) — it includes the skill plus authentication hooks and a code exploration subagent.

### Option 1: Skills (universal — 30+ agents)

Works with Cursor, GitHub Copilot, Windsurf, Gemini CLI, Codex, Goose, Amp, Roo Code, OpenCode, OpenClaw, and [others](https://agentskills.io/).

```bash
npx skills add CodeAlive-AI/codealive-skills@codealive-context-engine
```

Or copy the `skills/codealive-context-engine` folder into your agent's skills directory:

| Agent | Project scope | User scope |
|-------|--------------|------------|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| Cursor | `.cursor/skills/` | `~/.cursor/skills/` |
| GitHub Copilot | `.github/skills/` | `~/.copilot/skills/` |
| Windsurf | `.windsurf/skills/` | `~/.codeium/windsurf/skills/` |
| Gemini CLI | `.gemini/skills/` | `~/.gemini/skills/` |
| Codex | `.codex/skills/` | `~/.codex/skills/` |
| Goose | `.goose/skills/` | `~/.config/goose/skills/` |
| Amp | `.agents/skills/` | `~/.config/agents/skills/` |
| Roo Code | `.roo/skills/` | `~/.roo/skills/` |
| OpenCode | `.opencode/skill/` | `~/.config/opencode/skill/` |
| OpenClaw | `skills/` | `~/.openclaw/skills/` |

### Option 2: Claude Code Plugin

For Claude Code users, this repository also serves as a plugin marketplace with Claude-specific enhancements.

```
/plugin marketplace add CodeAlive-AI/codealive-skills
/plugin install codealive@codealive-marketplace
```

### Option 3: MCP Server

For deeper integration, install the [CodeAlive MCP server](https://github.com/CodeAlive-AI/codealive-mcp) — it gives your agent direct access to CodeAlive's tools via the Model Context Protocol. The skill and MCP server complement each other: the MCP server provides tool access, the skill teaches the agent how to use it effectively.

### Option 4: Share the Claude Code plugin with another agent

If you already use the Claude Code plugin and want Codex CLI, Gemini CLI, or another skill-aware agent to consume the exact same skill files, install the [plugin bridge](tools/plugin-bridge/) — a tiny `launchd` agent (macOS) or `systemd --user` path unit (Linux) that keeps a symlink from the other agent's skills directory into the plugin's versioned cache. It re-links automatically on `claude plugin update`.

```bash
cd tools/plugin-bridge
./install-macos.sh
```

See [`tools/plugin-bridge/README.md`](tools/plugin-bridge/README.md) for configuration and Linux instructions.

## Setup

After installing the skill, run the interactive setup:

```bash
python setup.py
```

This will ask for your [API key](https://app.codealive.ai/settings/api-keys), verify it, and store it securely in your OS credential store.

### API Key Storage

The API key is resolved in this order:

1. `CODEALIVE_API_KEY` environment variable
2. OS credential store:

| Platform | Store | Manual command |
|----------|-------|----------------|
| macOS | Keychain | `security add-generic-password -a "$USER" -s "codealive-api-key" -w "KEY"` |
| Linux | Secret Service | `secret-tool store --label="CodeAlive API Key" service codealive-api-key` |
| Windows | Credential Manager | `cmdkey /generic:codealive-api-key /user:codealive /pass:"KEY"` |

The key is stored once and shared across all agents on the same machine.

**Self-hosted instance:** set `CODEALIVE_BASE_URL` to your deployment origin, for example `https://codealive.yourcompany.com`. The setup script accepts both `https://host` and `https://host/api`, but the origin form is preferred.

## Usage

Start your agent and ask naturally:

- *"How is authentication implemented?"*
- *"Find the exact regex or string match for this token parser"*
- *"Show me error handling patterns across services"*
- *"Find similar features to guide my implementation"*
- *"Show me who calls this handler and what it depends on"*

No special commands needed — the agent picks up the skill automatically.

To check the installed skill version without authentication or a network request:

```bash
python skills/codealive-context-engine/scripts/get_version.py
```

## License

MIT
