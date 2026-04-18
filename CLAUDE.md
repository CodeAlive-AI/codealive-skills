# codealive-skills — notes for AI coding agents

This repository ships two things:

1. The **`codealive-context-engine` Agent Skill** — a `SKILL.md` plus a
   set of Python scripts (`scripts/datasources.py`, `search.py`,
   `grep.py`, `fetch.py`, `relationships.py`, `chat.py`).
2. A **Claude Code plugin** (`.claude-plugin/plugin.json`) that bundles
   the skill with authentication hooks and the
   `codealive-context-explorer` subagent.

## What the skill is NOT

The skill is **not an MCP wrapper** and does **not** expose MCP tools.
It is a set of Python scripts that call the CodeAlive REST API directly
over HTTPS, using an API key resolved from the OS credential store or
the `CODEALIVE_API_KEY` env var.

The [codealive-mcp](https://github.com/CodeAlive-AI/codealive-mcp)
server is a **separate product** that exposes CodeAlive as MCP tools
(`get_data_sources`, `semantic_search`, `grep_search`,
`fetch_artifacts`, `get_artifact_relationships`). The skill and the
MCP server are parallel integration paths — either works on its own,
and both can be installed alongside each other.

Do not conflate them when writing or reviewing skill descriptions,
docs, or commit messages.

## Architecture in one sentence

`SKILL.md` is workflow/trigger metadata; the scripts under
`skills/codealive-context-engine/scripts/` are the implementation; the
CodeAlive REST API is the backend. MCP is an optional sibling, not a
dependency.

## Releasing

1. Edit `SKILL.md`, scripts, or plugin assets.
2. Bump `.claude-plugin/plugin.json` `version`.
3. Commit, then annotate a tag matching `vX.Y.Z`.
4. Push `main` and the tag. CI (`.github/workflows/ci.yml`) runs
   `pytest tests -v` on push.
5. Users pick up the new version via `claude plugin update
   codealive@codealive-marketplace` or `npx skills update`.

## Writing the skill description

The `description` field in `SKILL.md` frontmatter is how agents decide
whether to load the skill. Keep it accurate and discoverable:

- Include the word **CodeAlive** so brand mentions match.
- Include concrete trigger verbs/nouns users actually say: *list data
  sources*, *indexed repositories*, *search across repos*, *fetch
  artifact content*, *call graph*.
- Do not claim to wrap MCP tools — see above.
- Do not bake in anti-patterns against specific failure modes of one
  session; the description is read by many agents in many contexts.
- Hard limit 1024 chars; aim for 300–500.
