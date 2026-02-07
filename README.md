# CodeAlive Skills

Agent skills for [CodeAlive](https://app.codealive.ai) — install via [skills.sh](https://skills.sh/) to any AI coding agent.

## Available Skills

| Skill | Description | Install |
|-------|-------------|---------|
| [codealive-context-engine](codealive-context-engine/) | Semantic code search and AI-powered codebase Q&A across indexed repositories | `npx skills add CodeAlive-AI/codealive-skills@codealive-context-engine` |

## Supported Agents

Works with any agent that supports the [SKILL.md](https://skills.sh/docs) format:

Claude Code, Cursor, GitHub Copilot, Windsurf, Gemini CLI, Codex, Goose, Amp, Roo Code, OpenCode, and others.

## Quick Start

### 1. Install

```bash
npx skills add CodeAlive-AI/codealive-skills@codealive-context-engine
```

Or copy the skill folder manually into your agent's skills directory:

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

### 2. Set up

```bash
python setup.py
```

The interactive setup will ask for your [API key](https://app.codealive.ai/settings/api-keys), verify it, and store it securely in your OS credential store.

### API Key Storage

The setup script (and the skill at runtime) resolves the API key in this order:

1. `CODEALIVE_API_KEY` environment variable
2. OS credential store:

| Platform | Store | How to save manually |
|----------|-------|---------------------|
| macOS | Keychain | `security add-generic-password -a "$USER" -s "codealive-api-key" -w "KEY"` |
| Linux | freedesktop Secret Service | `secret-tool store --label="CodeAlive API Key" service codealive-api-key` |
| Windows | Credential Manager | `cmdkey /generic:codealive-api-key /user:codealive /pass:"KEY"` |

The key is stored once and shared across all agents on the same machine — no need to configure each agent separately.

**Self-hosted instance:** set `CODEALIVE_BASE_URL` env var to your instance URL.

### 3. Use

Start your agent and ask naturally:

- *"How is authentication implemented?"*
- *"Show me error handling patterns across services"*
- *"Find similar features to guide my implementation"*

No special commands needed — the agent picks up the skill automatically.

## License

MIT
