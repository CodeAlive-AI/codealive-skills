---
name: codealive-context-engine
description: Semantic search, grep, and Q&A across codebases and documentation indexed in CodeAlive. Use when the user mentions "CodeAlive", asks to list or get data sources, list indexed repositories, search code or docs across remote repos, fetch artifact content, or trace call graphs across repositories.
---

# CodeAlive Context Engine

Semantic code intelligence across your entire code ecosystem — current project, organizational repos, dependencies, and any indexed codebase.

## Authentication

All scripts require a CodeAlive API key. If any script fails with "API key not configured", help the user set it up:

**Option 1 (recommended):** Run the interactive setup and wait for the user to complete it:
```bash
python setup.py
```

**Option 2 (not recommended — key visible in chat history):** If the user pastes their API key directly in chat, save it via:
```bash
python setup.py --key THE_KEY
```

Do NOT retry the failed script until setup completes successfully.

## Table of Contents

- [Authentication](#authentication)
- [Tools Overview](#tools-overview)
- [When to Use](#when-to-use)
- [Quick Start](#quick-start)
- [Tool Reference](#tool-reference)
- [Data Sources](#data-sources)
- [Configuration](#configuration)

## Tools Overview

| Tool | Script | Speed | Cost | Best For |
|------|--------|-------|------|----------|
| **List Data Sources** | `datasources.py` | Instant | Free | Discovering indexed repos and workspaces. With `--query "task"`, runs an AI relevance filter (low cost, not instant) returning only the relevant sources |
| **Semantic Search** | `search.py` | Fast | Low | Default discovery — finds code by meaning (concepts, behavior, architecture) |
| **Grep Search** | `grep.py` | Fast | Low | Finds code containing a specific string or regex (identifiers, literals, patterns) |
| **Repository Ontology** | `ontology.py` | Fast | Low | High-level orientation for exactly one repository |
| **File Tree** | `tree.py` | Fast | Free | Bounded repository tree inspection |
| **Read File** | `read_file.py` | Fast | Free | Read one repository-relative file path, optionally with a line range |
| **Fetch Artifacts** | `fetch.py` | Fast | Free | Retrieve full content for search result identifiers |
| **Artifact Relationships** | `relationships.py` | Fast | Free | Full call graph, inheritance, or symbol references for one artifact |
| **ArtifactQuery Schema** | `schema.py` | Fast | Free | Inspect supported metadata query entities, fields, and examples |
| **Artifact Metadata Query** | `metadata.py` | Fast | Low | Read-only aggregate/query analytics across indexed repositories |
| **Chat with Codebase** | `chat.py` | Slow | High | Stateless synthesized Q&A. Call ONLY when the user explicitly asks. |

**Cost guidance:** `semantic_search` and `grep_search` are the default starting point — fast and cheap. Use `fetch_artifacts` to load full source and `get_artifact_relationships` to trace call graphs. All four tools are low-cost.

**Chat is not recommended:** `chat.py` invokes an LLM on the server side, can take substantially longer than retrieval, and is significantly more expensive per call. It is stateless in v3: include prior findings, artifact identifiers, assumptions, scope, and constraints in each question. Do NOT call it unless the user has explicitly requested it (e.g. "use chat", "call the chat tool"). Phrases like "ask CodeAlive" or "search CodeAlive" do NOT qualify — they refer to search tools.

**Repairable tool errors:** Treat a returned `<tool_error>` as a failed call,
not as an empty successful result. Follow its `<try>` guidance, repair the
arguments, and retry only when the `<retry>` field permits it. Tool API v3
always preserves the same error in `obj.error` for JSON-mode automation.

**Highest-confidence guidance:** If your agent supports subagents and the task needs maximum reliability or depth, prefer a subagent-driven workflow that combines `ontology.py`, `search.py`, `grep.py`, `fetch.py`, `tree.py`/`read_file.py`, `relationships.py`, `metadata.py`, and local file reads.

**Three-step workflow (search → triage → load real content):**
1. **Search** — find relevant code locations with descriptions and identifiers
2. **Triage** — use `description` ONLY to decide which results are worth a closer
   look. It is a pointer, NOT the source of truth. Do not draw conclusions from it.
3. **Get real content** — for every artifact you decide is relevant:
    - External repos (no local access): `python fetch.py <identifier>`
    - Current working repo: read the file at the shown path with your editor's
      file-read tool
    Treat only that real `content` as ground truth.

**Drill into `relationships.py` when the fetch preview isn't enough.** The
`fetch.py` response already previews up to 3 outgoing + 3 incoming calls for
function-like artifacts, so the call graph alone is rarely a reason to run
`relationships.py` after a full fetch of a small artifact. Reach for it when:

- **You need all incoming callers** — the fetch preview is capped at 3.
  The full incoming list also surfaces test coverage (incoming from test
  files).
- **You need the inheritance tree** — `--profile inheritanceOnly` returns
  ancestors + descendants (interface implementations, subclasses, base-class
  chains). The preview doesn't include inheritance.
- **You need symbol references** — `--profile referencesOnly` for places
  that reference a type or identifier.
- **The artifact is too large to fetch into context** — the call graph is a
  cheaper summary than pulling the full source.

**Analyzer noise:** outgoing calls occasionally include compiler-generated
helpers (`MoveNext`, `GetEnumerator`, closure invocations) from methods using
`foreach`/LINQ. Ignore outgoing hits that don't match the artifact's real
logic.

## When to Use

**Semantic search (default) — you describe behavior or concept:**
- "How is authentication implemented?"
- "Show me error handling patterns across services"
- "How does this library work internally?"
- "Find similar features to guide my implementation"

**Grep search — you know the exact text:**
- "Find all usages of `RepositoryDeleted`"
- "Where is `ConnectionString` configured?"
- "Search for `TODO: fix` across the codebase"
- Error messages, URLs, config keys, import paths, regex patterns

**Use local file tools instead for:**
- Finding specific files by name or pattern
- Exact keyword search in the current directory
- Reading known file paths
- Searching uncommitted changes

## Quick Start

### 1. Discover what's indexed

```bash
python scripts/datasources.py --query "the user's task in natural language"
```

Recommended: pass the user's task as `--query` so the backend returns only the relevant
data sources, each with a `relevanceReason`. Omit `--query` to list everything (instant,
no AI filtering).

### 2. Search for code (fast, cheap)

```bash
python scripts/search.py "JWT token validation" my-backend
python scripts/search.py "authentication flow" my-repo --path src/auth --ext .py
python scripts/grep.py "AuthService" my-repo
python scripts/grep.py "auth\\(" my-repo --regex
```

### 3. Fetch full content (for external repos)

```bash
python scripts/fetch.py "my-org/backend::src/auth.py::AuthService.login()"
```

### 4. Drill into an artifact's relationships (optional)

```bash
# Full call graph (default)
python scripts/relationships.py "my-org/backend::src/auth.py::AuthService.login()"

# Inheritance hierarchy for a class
python scripts/relationships.py "my-org/backend::src/models.py::User" --profile inheritanceOnly

# Calls + inheritance, raise the per-type cap
python scripts/relationships.py "my-org/backend::src/svc.py::Service" --profile allRelevant --max-count 200
```

### 5. Chat with codebase (not recommended — only if user explicitly asks)

```bash
python scripts/chat.py "Explain the authentication flow. Prior context: none." my-backend
python scripts/chat.py "Given these prior findings and identifiers: ..., what about security considerations?" my-backend
```

**Do not call chat unless the user explicitly asks for it.** v3 chat is stateless and has no `conversation_id`; include all needed context in each question. Use ontology, search, grep, fetch/read, relationships, and metadata queries for all other tasks.

## Tool Reference

### `datasources.py` — List Data Sources

```bash
python scripts/datasources.py --query "add OAuth to checkout"  # Only sources relevant to a task (recommended)
python scripts/datasources.py              # Ready-to-use sources (full list)
python scripts/datasources.py --all        # All (including processing)
python scripts/datasources.py --json       # JSON output
```

| Option | Description |
|--------|-------------|
| `--query "TASK"` | The user's task/intent in natural language. The backend runs an AI relevance filter and returns only the relevant sources, each with a `relevanceReason`. Recommended whenever you know what the user is trying to accomplish |
| `--all` | Include sources still processing |
| `--json` | Raw JSON output (with `--query`: `{"dataSources": [...], "message": "..."}`) |

**Fail-open:** if relevance filtering is unavailable, the FULL list is returned and the
output says so — check the message before treating the result as a relevant shortlist.

### `search.py` — Semantic Code Search (default discovery tool)

The default starting point. Finds code by WHAT it does — concepts, behavior,
architecture — not by exact text. Use when you can describe what you're
looking for but don't know the exact names in the codebase.

```bash
python scripts/search.py <query> <data_sources...> [options]
```

| Option | Description |
|--------|-------------|
| `--max-results N` | Optional cap for the number of returned artifacts |
| `--path PATH` | Repo-relative path or directory scope (repeatable) |
| `--ext EXT` | File extension scope such as `.py` or `.ts` (repeatable) |

**`description` is a triage pointer ONLY** — it tells you which artifacts are
worth a closer look. It is NOT the source of truth and you must NOT draw
conclusions from it. For every result you consider relevant, load the real
source: use `fetch.py <identifier>` for external repos, or your editor's
file-read tool on the path for repos in the current working directory. Treat
only that real `content` as ground truth.

### `grep.py` — Exact Text / Regex Search

Finds code containing a specific string or regex pattern. Use when you know
the exact text to look for: identifiers, error messages, config keys, URLs,
domain events, import paths, TODO comments.

```bash
python scripts/grep.py <query> <data_sources...> [--regex] [--max-results N] [--path PATH] [--ext EXT]
```

| Option | Description |
|--------|-------------|
| `--regex` | Interpret the query as a regex pattern |
| `--max-results N` | Optional cap for the number of returned artifacts |
| `--path PATH` | Repo-relative path or directory scope (repeatable) |
| `--ext EXT` | File extension scope such as `.py` or `.ts` (repeatable) |

Line previews are still search evidence, not source of truth. Use `fetch.py`
or your local file-read tool before drawing conclusions about behavior.

### `fetch.py` — Fetch Artifact Content

Retrieves the full source code content for artifacts found via search. Use this for external repositories you cannot access locally.

```bash
python scripts/fetch.py <identifier1> [identifier2...] [--data-source NAME_OR_ID]
```

| Constraint | Value |
|-----------|-------|
| Max identifiers per request | 50 |
| Identifiers source | `identifier` field from search results |
| Identifier format | `{owner/repo}::{path}::{symbol}` (symbols), `{owner/repo}::{path}` (files) |
| `--data-source NAME_OR_ID` | Optional. Data source Name or Id (from a result's `Source:` line) to disambiguate an identifier indexed in more than one data source |

For function-like artifacts the response includes a small **relationships
preview** (up to 3 outgoing/incoming calls per direction). To see the full
call graph, inheritance, or references, run `relationships.py` with the
artifact's identifier.

**Missing identifiers.** If an identifier cannot be resolved (or is outside your access
scope), `fetch.py` does not drop it silently — it prints a "not found" section listing each
concrete identifier, with a hint to re-check those ids and retry the problematic ones. Tell
the user which artifacts could not be fetched instead of omitting them.

**Disambiguating an identifier that lives in more than one data source.** Artifact
identifiers are unique only per data source, so the same identifier can belong to
more than one data source. If you fetch such an identifier without `--data-source`,
the backend returns a **409** listing the candidate data sources instead of picking
one for you. Every listed candidate **will** resolve, so the workflow is: call without
`--data-source` → read the 409 candidates → try one → if that data source isn't the one
you want, try the next. To resolve it: take the
`Source:` name or id shown next to the search result you want and pass it back —
`python scripts/fetch.py <identifier> --data-source "backend"` (or the id).
The same `--data-source` flag works on `relationships.py`. If a `--data-source`-scoped
call finds nothing (the script prints a "nothing was found in data source …" hint),
the identifier belongs to a different data source or the selector is wrong: retry with
a different `Source:` value, or drop `--data-source` to get the 409 candidate list.

### `relationships.py` — Drill into an Artifact's Relationship Graph

Returns the full call graph (incoming/outgoing calls), inheritance hierarchy
(ancestors/descendants), or symbol references for a single artifact. This is
the drill-down tool — use it AFTER `search.py` or `fetch.py` once you have an
identifier and want to understand how the artifact relates to the rest of the
codebase.

```bash
python scripts/relationships.py <identifier> [--profile PROFILE] [--max-count N] [--data-source NAME_OR_ID]
```

| Option | Description |
|--------|-------------|
| `--profile callsOnly` | Default. Outgoing + incoming calls |
| `--profile inheritanceOnly` | Ancestors + descendants |
| `--profile allRelevant` | Calls + inheritance (4 groups) |
| `--profile referencesOnly` | Symbol references |
| `--max-count N` | Max related artifacts per relationship type (1–1000, default 50) |
| `--data-source NAME_OR_ID` | Optional. Data source Name or Id to disambiguate an identifier indexed in more than one data source (same 409 contract as `fetch.py`) |
| `--json` | Emit the raw JSON response instead of the formatted view |

**When this adds value vs the fetch preview:**
- You need **all incoming callers** (including tests) — the fetch preview
  caps at 3 per direction
- You need the **inheritance tree** (`--profile inheritanceOnly`) — preview
  doesn't include ancestors/descendants
- You need **symbol references** (`--profile referencesOnly`) — preview
  doesn't include references
- The artifact is too large to fetch into context

**When it's usually redundant:** you already ran `fetch.py` on a small
artifact that fits in context. The outgoing calls you need are either in the
source you just read or in the preview's 3-cap — reach for `relationships.py`
only when you specifically need incoming calls, inheritance, or references.

**Noise caveat:** outgoing calls occasionally include compiler-generated
helpers (`MoveNext`, `GetEnumerator`, closure invocations) for methods using
`foreach`/LINQ. These are analyzer artifacts — ignore outgoing hits that
don't match the artifact's real logic.

### `chat.py` — Chat with Codebase (not recommended)

**Do NOT call unless the user explicitly asks** (e.g. "use chat", "call the chat tool"). Phrases like "ask CodeAlive" or "search CodeAlive" refer to search tools, not chat.

Sends your self-contained question to an AI consultant that has full context of the selected indexed codebase. Returns synthesized, ready-to-use answers.

**This is slow and expensive** — runs an LLM on the server side and can take substantially longer than retrieval. It is stateless in v3, so include prior findings, identifiers, assumptions, scope, and constraints in each question. For all standard tasks (finding code, understanding architecture, debugging), use ontology, search, grep, fetch/read, relationships, and metadata queries instead.

```bash
python scripts/chat.py <question> <data_sources...> [options]
```

There is no public `conversation_id` in v3. For follow-ups, restate the relevant context in the next `question`.

## Data Sources

**Repository** — single codebase, for targeted searches:
```bash
python scripts/search.py "query" my-backend-api
```

**Workspace** — multiple repos, for cross-project patterns:
```bash
python scripts/search.py "query" workspace:backend-team
```

**Multiple repositories:**
```bash
python scripts/search.py "query" repo-a repo-b repo-c
```

## Configuration

### Prerequisites

- Python 3.8+ (no third-party packages required — uses only stdlib)

### API Key Setup

The skill needs a CodeAlive API key. Resolution order:

1. `CODEALIVE_API_KEY` environment variable
2. OS credential store (macOS Keychain / Linux secret-tool / Windows Credential Manager)

**Environment variable (all platforms):**
```bash
export CODEALIVE_API_KEY="your_key_here"
```

**macOS Keychain:**
```bash
security add-generic-password -a "$USER" -s "codealive-api-key" -w "YOUR_API_KEY"
```

**Linux (freedesktop secret-tool):**
```bash
secret-tool store --label="CodeAlive API Key" service codealive-api-key
```

**Windows Credential Manager:**
```cmd
cmdkey /generic:codealive-api-key /user:codealive /pass:"YOUR_API_KEY"
```

**Base URL** (optional, defaults to `https://app.codealive.ai`):
```bash
export CODEALIVE_BASE_URL="https://your-instance.example.com"
```

For self-hosted CodeAlive, use your deployment origin. `https://your-instance.example.com` is preferred, but `https://your-instance.example.com/api` is also accepted and normalized automatically.

Get API keys at: https://app.codealive.ai/settings/api-keys

## Using with CodeAlive MCP Server

This skill works standalone, but delivers the best experience when combined with the [CodeAlive MCP server](https://github.com/CodeAlive-AI/codealive-mcp). The MCP server provides direct tool access via the Model Context Protocol, while this skill provides the workflow knowledge and query patterns to use those tools effectively.

| Component | What it provides |
|-----------|-----------------|
| **This skill** | Query patterns, workflow guidance, cost-aware tool selection |
| **MCP server** | Direct `semantic_search`, `grep_search`, `fetch_artifacts`, `get_artifact_relationships`, `get_data_sources` tools via MCP protocol |

When both are installed, prefer the MCP server's tools for direct operations and this skill's scripts for guided workflows.

## Detailed Guides

For advanced usage, see reference files:
- **[Query Patterns](references/query-patterns.md)** — effective query writing, anti-patterns, language-specific examples
- **[Workflows](references/workflows.md)** — step-by-step workflows for onboarding, debugging, feature planning, and more
