# CodeAlive Context Engine: Freshness & Trust Design v2

## Status

Final design document. Evolved through five rounds:
1. FPF-guided brainstorm session (2026-03-17)
2. Consilium review by Codex (GPT-5.4) and Gemini (3.1 Pro) — independent analysis
3. Design revision incorporating external critique and user decisions (2026-03-18)
4. UX analysis against Laws of UX principles — validated design, added branch header to fetch.py (2026-03-18)
5. Consilium v2 FPF review — divergence direction model, Strategy 2 removal, agent instruction refinement (2026-03-18)

## Table of Contents

- [Problem Statement](#problem-statement)
- [Scenarios](#scenarios)
- [Reasoning Chain](#reasoning-chain)
- [Candidate Hypotheses](#candidate-hypotheses)
- [External Review Findings](#external-review-findings)
- [UX Analysis](#ux-analysis)
- [Consilium v2 Review Findings](#consilium-v2-review-findings)
- [Final Design: Freshness Detector](#final-design-freshness-detector)
- [Implementation Plan](#implementation-plan)

---

## Problem Statement

The CodeAlive Context Engine provides semantic code search and AI-powered Q&A across indexed repositories. The cloud index is built from a specific commit on a specific branch. When the developer's local state diverges from that indexed state, the agent receives stale data without any indication of staleness.

This affects all scripts in the skill:

- **search.py** returns descriptions, line numbers, and identifiers based on outdated code
- **fetch.py** returns content from the cloud index that may not match local files
- **chat.py** synthesizes answers from stale context
- **explore.py** was removed (agent orchestrates search+chat workflow itself)

The agent has no mechanism to detect or handle this divergence. It treats all data as ground truth.

## Scenarios

Five distinct staleness scenarios:

| # | Scenario | What happens | Current behavior |
|---|----------|-------------|-----------------|
| 1 | **File modified locally** (same branch, uncommitted/unpushed changes) | Cloud index has old content; line numbers may have shifted | Agent works with stale data silently |
| 2 | **Different local branch** | Cloud indexed `main`, developer is on `feature/xyz`; entire file tree may differ | Agent has no idea results are from a different branch |
| 3 | **File deleted locally** (repo exists) | Cloud returns content for a file that no longer exists locally | Agent tries to Read() the file and gets an error |
| 4 | **Repo not cloned locally** (by design) | Developer intentionally does not have the repo on their machine | Normal use case for cloud data — **not a problem** |
| 5 | **New files locally** | Developer added files that the cloud index does not know about | Agent misses relevant context |

Scenario 4 is the only one where cloud-only data is correct and expected. Scenarios 1-3 produce incorrect data. Scenario 5 produces incomplete data.

## Reasoning Chain

### FPF Pattern Mapping

The analysis was guided by three FPF patterns from the First Principles Framework:

**B.3.4 Evidence Decay & Epistemic Debt.** The cloud index is an evidence artifact with a perishable validity window. Its trustworthiness decays as local state diverges. The `valid_until` concept maps directly to the indexed commit — once the local repo moves past that commit, the evidence (cloud data) begins to accrue "epistemic debt."

| FPF concept | Our domain |
|---|---|
| Evidence artifact | Indexed artifact (file, symbol, description) |
| `valid_until` | Indexed commit hash + timestamp |
| Epistemic Debt | Divergence: commits ahead, modified files, branch mismatch |
| Refresh | Agent reads local file via Read() — the actual "refresh" action |
| Deprecate | Filter out deleted files (evidence no longer valid) |
| Waive | Accept cloud data for external repos — scenario 4 |

**B.3 Trust & Assurance Calculus (F-G-R).** Each cloud artifact has a Reliability (R) that drops when local state diverges:

| Local file status | Reliability of cloud data | Action |
|---|---|---|
| Unchanged | R = high | Serve cloud data as-is |
| Modified | R = low | Redirect agent to read locally |
| Deleted | R = 0 | Filter out, do not show |
| Missing (branch mismatch) | R = uncertain | Serve cloud data with branch note |
| Repo not local | R = waived | Serve cloud data (normal mode) |

**B.3 WLNK (Weakest Link).** If even one result in a set is stale, the overall search may have missed something relevant. This means the summary must signal that the result set is potentially incomplete — not just that individual results are stale.

### Key Design Decisions

**Decision 1: `--repo-path` is mandatory.**

The agent must pass `--repo-path <path>` or `--repo-path none` on every call. Without it, the script returns a clear error with explanation, asking the agent to retry. This forces the agent to be explicit about whether a local repo is available — making the trust decision conscious, not accidental.

Why mandatory, not optional: LLMs unreliably pass optional parameters (FPF WLNK — the weakest link in the trust chain is agent compliance). An optional parameter that the agent forgets silently disables the entire freshness system. A mandatory parameter that the agent omits produces a loud, recoverable error.

Why not auto-detection: Early designs included `LocalRepoRegistry` with four auto-detection strategies. This was overengineered. The agent knows its working directory. One CLI argument replaces ~100 lines of detection code.

```bash
# Agent has repo locally
python search.py "auth" my-backend --repo-path /path/to/my-backend

# Agent does not have repo locally
python search.py "auth" external-lib --repo-path none
```

**Decision 2: The skill is a freshness DETECTOR, not a content DELIVERER.**

Early designs had scripts reading local files and returning their content to the agent ("smart data broker" pattern). This was fragile:
- Cloud line numbers drift when files are modified — reading local file at stale line range gives wrong content
- Symbol/chunk identifiers can't be reconstructed locally without a parser
- Output contract changes when local content replaces cloud content

The correct principle: **the skill detects staleness and tells the agent what to do. The agent reads local files itself using Read().**

This plays to each component's strengths:
- Skill has: git access, cloud API, semantic search, artifact metadata
- Agent has: Read() tool, full local filesystem access, reasoning ability

| Aspect | Rejected (data broker) | Adopted (freshness detector) |
|---|---|---|
| Modified files | Script reads local file, returns content | Script says "modified locally — read with Read()" |
| Line drift bug | Fatal — stale line numbers → wrong content | Eliminated — script gives approximate lines as hint |
| Symbol parsing | Needs local parser per language | Not needed — agent reads the file |
| Content hashing | Needed for per-artifact precision | Not needed — git status is sufficient |
| Output contract | Changes (local content ≠ cloud format) | Stable (cloud content + annotations) |
| Implementation | Complex (hash, read, route, format) | Simple (git status + annotate) |

**Decision 3: Mixed annotation format — per-artifact markers + compact summary.**

Neither fully silent (agent can't act on information it doesn't receive) nor verbose (per-result trust tuples overload context window). The design uses:

1. Per-artifact inline markers for modified/deleted results
2. One-line summary footer with counts
3. All line numbers marked as approximate for modified files

Context overhead: ~30-50 tokens per call (vs ~200 for chatty design, ~20 for fully silent).

**Decision 4: Divergence has direction — "different" ≠ "prefer local".**

Consilium v2 review (Codex) identified a critical gap: `git diff` reports which files differ, but NOT which side is newer. If the developer hasn't pulled and local is behind the indexed commit, redirecting to `Read()` gives OLDER data, not fresher. The resolution policy must depend on the direction of divergence:

| Direction | Meaning | Resolution |
|---|---|---|
| `exact` | Same commit, clean working tree | Cloud = ground truth |
| `local_ahead` | HEAD descends from indexed commit (or has uncommitted changes) | Local is newer → Read() |
| `local_behind` | Indexed commit descends from HEAD (dev hasn't pulled) | Cloud is newer → use cloud, warn to pull |
| `diverged` | Neither is ancestor of the other (branches forked) | Both sides changed → warn, suggest Read() + note cloud version |
| `unknown` | Indexed commit not available locally | Degraded mode → warn, Read() as best effort |

Direction is determined via `git merge-base --is-ancestor`. This adds one git call but eliminates the most dangerous failure mode — silently serving older data as "fresh."

**Decision 5: Strategy 2 (`origin/<branch>`) removed — exact-or-degraded model.**

The v2 design had a 3-strategy fallback. Consilium v2 review (Codex, Gemini) independently identified Strategy 2 as unsafe: `origin/<branch>` is not a substitute for the actual indexed commit. Under FPF B.5.2, when discriminating evidence is unavailable, the honest response is "defer/degraded," not a surrogate pretending to be precise.

New model: **2-strategy fallback.**
1. **Exact**: indexed commit exists locally → precise diff + direction detection
2. **Degraded**: indexed commit not found → only uncommitted changes + repo-level warning

## Candidate Hypotheses

Five candidates were generated and evaluated using FPF B.5.2 Abductive Loop plausibility filters (Explanatory Reach, Parsimony, Falsifiability, Consistency, Scope Fit):

### A: Full Trust Layer

Every artifact carries a trust tuple. Agent interprets labels and acts accordingly.

- Rejected: overloads the agent, non-deterministic behavior, ~200 tokens overhead per call.

### B: Smart Fetch Only

Focus solely on fetch.py as the critical pain point. Other scripts unchanged.

- Insufficient: search descriptions and line numbers remain stale, agent gets no freshness signal.

### C: Dual Index (Local Overlay)

Build a lightweight local index (git diff + file hashes) as an overlay on cloud results.

- Partially retained: the git state snapshot concept is used in the final design.
- Local overlay search for new files deferred to future work.

### D: Backend-First Freshness

API accepts local context (commit, branch, modified files) and filters server-side.

- Partially retained: backend returns indexing metadata per data source (commit, branch, indexedAt).
- Sending dirty file lists to server rejected for now (unnecessary when client can check locally).

### E: Composite Data Broker (v1 design)

Combine backend metadata + local git state + content hash + smart routing. Scripts read local files and return fresh content directly.

- Was the prime hypothesis in v1. Superseded after external review revealed critical flaws (line drift bug, symbol parsing impossibility, hash weakness).

### F: Freshness Detector (v2 design — selected)

Scripts detect staleness via git state and annotate results. Agent reads modified files itself via Read(). No local file reading by scripts, no content hashing.

- Selected because: eliminates all v1 flaws, simpler implementation, stable output contract, plays to each component's strengths, minimum viable trust signal for the agent.

## External Review Findings

Two independent AI agents (Codex/GPT-5.4 as Rigorous Analyst, Gemini/3.1 Pro as Lateral Thinker) reviewed the v1 design. Key findings that drove the v2 revision:

### Critical flaws found (both agents independently)

1. **Line number drift bug**: Cloud line numbers are stale for locally modified files. Reading local file at stale line ranges gives wrong content. Hash comparison then draws wrong trust conclusion. → **Fixed in v2**: scripts don't read local files at all; they redirect agent to Read().

2. **Hash algorithm too weak**: Adler-32 reduced to 30 bits is insufficient for trust arbitration. → **Fixed in v2**: content hashing eliminated entirely. Git status is sufficient when the skill is a detector, not a deliverer.

3. **Scenario 5 not solved**: v1 claimed coverage of all 5 scenarios but provided no mechanism to discover new local files. → **Acknowledged in v2**: script reports untracked file count; full local search deferred.

### Additional findings incorporated

4. **Symbol/chunk identifiers can't be locally reconstructed** (Codex): Client has no parser, no symbol boundary logic, no chunking logic. → **Fixed in v2**: agent reads files itself.

5. **chat.py fundamentally incompatible with client-side freshness** (Codex): It's a server-side RAG pipeline; client annotation doesn't make retrieval fresher. → **Acknowledged in v2**: chat.py gets branch note only; deeper fix requires backend changes.

6. **Silent deletion filtering loses signal** (Codex): "Index thinks this exists but local doesn't" is material information. → **Fixed in v2**: deleted files noted in summary footer.

7. **Agent non-compliance risk** (Gemini, FPF WLNK): Optional `--repo-path` silently disables freshness when forgotten. → **Fixed in v2**: `--repo-path` is mandatory with clear error message.

8. **One `--repo-path` insufficient for multi-repo/workspace** (Codex): Skill supports multiple repos and workspaces. → **Addressed in v2**: `--repo-path` applies to the first matching data source; for workspace queries, script matches artifact paths against repo root.

9. **Existing code has bugs** (Codex): `explore.py` passes `include_content` to `client.search()` which doesn't accept it. → **Resolved**: explore.py removed from the skill.

## UX Analysis

UX principles from Laws of UX applied to the freshness detector design. Our "user" is an AI coding agent, but the output is ultimately consumed by a human developer.

### Principles that validate existing design

| UX Principle | Design Decision It Validates |
|---|---|
| **Tesler's Law** (absorb complexity in the system) | Skill absorbs git complexity (3-strategy fallback, commit diffing); agent sees only simple annotations |
| **Progressive Disclosure** (simple by default, powerful when needed) | Three-level annotation: no marker for fresh results → inline marker for divergent → summary footer for big picture |
| **Cognitive Load / Chunking** | Variant B (separate dataSources array) — one object per data source instead of duplicating metadata in every result |
| **Von Restorff Effect** (distinct item is remembered) | `!! MODIFIED LOCALLY` prefix breaks the uniform pattern of normal results, making stale items immediately noticeable |
| **Postel's Law** (liberal input, conservative output) | 3-strategy fallback accepts degraded input (missing indexed commit); `--repo-path` accepts path/relative/none |
| **Doherty Threshold** (< 400ms) | `git diff --name-only` is ~10-50ms; GitState is lazy-evaluated and cached per invocation |
| **Error Handling** (Prevention > Recovery > Graceful Failure) | Mandatory `--repo-path` prevents silent bypass; clear error with usage example enables recovery on first retry |

### Refinement 1: Serial Position Effect — branch header on ALL scripts

Users best remember the first and last items in a series. The most severe freshness signal (branch mismatch) should appear at both the TOP (primacy effect) and BOTTOM (recency effect) of output.

search.py already had a branch header. This refinement extends it to **fetch.py** and makes the pattern explicit: whenever `branch_matches == False`, every script emits a one-line header before any results.

### Refinement 2: Error message format — `[What's wrong] + [How to fix it]`

The `--repo-path` error message follows UX error handling best practices: state the problem, explain why it matters, show exactly how to fix it with copy-pasteable examples. This maximizes agent recovery on first error.

## Consilium v2 Review Findings

Second Consilium review of the v2 design, both agents reviewing through FPF lens.

### Critical findings (both agents)

1. **"Divergent ≠ prefer local"** (Codex): If local HEAD is *behind* the indexed commit, `git diff` still reports changed files, but the cloud is *newer*. Redirecting to `Read()` gives older data. → **Fixed**: Added divergence direction detection (Decision 4).

2. **Strategy 2 (`origin/<branch>`) is unsafe** (Codex + Gemini): Under FPF B.5.2, when discriminating evidence is unavailable, honest answer is "defer/degraded," not a surrogate. → **Fixed**: Removed Strategy 2, simplified to exact-or-degraded (Decision 5).

### Codex-specific findings

3. **FPF mapping is partial** — design models only R (reliability), but search completeness = G (ClaimScope), repo-path↔datasource matching = CL (Congruence). → **Acknowledged**: Added G/CL to FPF Traceability appendix. Full F-G-R-CL conformance deferred.

4. **WLNK underapplied at result-set level** — committed new files on feature branch are not "untracked" but still missing from cloud index. → **Acknowledged**: Untracked count expanded to include committed-but-not-indexed files where detectable via diff.

5. **chat.py has no citation surface** — backend doesn't return which files were referenced in chat answers, so "N files modified" is not implementable. → **Acknowledged**: chat.py freshness limited to repo-level note only.

6. **`git diff --name-only` needs `-z` flag** for safe path handling with special characters. → **Adopted** in GitState implementation.

### Gemini-specific findings

7. **Git diff simplification** — `git diff --name-only <commit>` (without `..HEAD`) compares working tree directly to indexed commit, capturing committed + staged + unstaged in one command. → **Adopted**: Eliminates redundant second command.

8. **Monorepo path mismatch** — if cloud indexed a subdirectory, `rel_path` from cloud won't match git diff paths from repo root. → **Fixed**: Use suffix matching in `file_status()`.

9. **Agent psychology: approximate line numbers** — LLMs will literally call `Read(start_line=45, end_line=67)` even when told "approximate." → **Fixed**: Modified files now explicitly instruct "Read the entire file" without line ranges.

10. **Shallow clone collapse** — `--depth 1` means indexed commit is absent, silently degrading to Strategy 3 without hard signal. → **Acknowledged**: Handled by the exact-or-degraded model; degraded mode emits explicit warning.

## Final Design: Freshness Detector

### Architecture

```
Agent knows: working dir = /path/to/repo
         |
         |  --repo-path /path/to/repo  (mandatory)
         v
+---------------------------------------------------+
|  Script (search.py / fetch.py / ...)              |
|    +-- Cloud API call --> results + indexing meta  |
|    +-- GitState(repo_path, indexed_commit)         |
|    +-- git diff <indexed_commit> (working tree)    |
|    +-- Divergence direction (ahead/behind/diverged)|
|    +-- Per-artifact status check                   |
|    +-- Direction-aware annotated output to agent   |
|    +-- Summary footer                              |
+---------------------------------------------------+
         |
         |  "src/auth.py modified locally,
         |   read with Read() at ~line 45"
         v
    Agent uses Read() for modified files
```

### Core principle: Separation of Detection and Resolution

The skill DETECTS freshness issues. The agent RESOLVES them.

| Component | Responsibility |
|---|---|
| **Script** | Diff local state against indexed commit, annotate results, filter deleted, report branch mismatch |
| **Agent** | Read modified/new files locally via Read(), use approximate line numbers as hints |
| **Backend** | Provide indexing metadata (commit, branch, timestamp) per data source |

### Layer 1: Backend Metadata

API responses include a top-level `dataSources` array with indexing metadata per data source. This avoids duplicating metadata in every result (20 results from one repo = 20 copies of the same commit hash would waste agent context).

**Search response structure (Variant B — separate dataSources array):**

```json
{
  "results": [
    {
      "kind": "Symbol",
      "dataSource": { "type": "repository", "id": "67f...", "name": "my-backend" },
      "identifier": "my-org/backend::src/auth.py::AuthService.validate_token",
      "location": { "path": "src/auth.py", "range": { "start": { "line": 45 }, "end": { "line": 67 } } },
      "description": "Validates JWT tokens..."
    }
  ],
  "dataSources": [
    {
      "id": "67f...",
      "name": "my-backend",
      "type": "repository",
      "indexing": {
        "commit": "abc123def",
        "branch": "main",
        "indexedAt": "2026-03-17T10:00:00Z"
      }
    }
  ]
}
```

**Fetch (artifacts) response — same pattern:**

```json
{
  "artifacts": [ ... ],
  "dataSources": [
    {
      "id": "67f...",
      "name": "my-backend",
      "type": "repository",
      "indexing": { "commit": "abc123def", "branch": "main", "indexedAt": "..." }
    }
  ]
}
```

**Script flow:** On response, the script does one pass over `dataSources` to extract the `indexed_commit` for the repo matching `--repo-path`, creates `GitState(repo_path, indexed_commit)`, then annotates results. No per-result metadata duplication.

**Backend implementation (SearchController.cs):**
- `SearchResponse` gets a new field: `List<DataSourceInfoDto> DataSources`
- `ArtifactContentResponse` gets the same field
- `DataSourceInfoDto` = `{ Id, Name, Type, Indexing: { Commit, Branch, IndexedAt } }`
- Populated from `selectedDataSources` (which already has `Branch`) + `ProcessingInfo.ProcessedCommitId` + `ProcessingInfo.LastProcessedAt`
- Existing `DataSourceDto` inside each result stays unchanged (no breaking change)

This is a **prerequisite** for client-side freshness detection. The `indexing.commit` field is critical: it enables `git diff --name-only <indexed_commit>` which compares the working tree directly to the indexed state, capturing committed + staged + unstaged changes in one command. Without it, `git status` alone cannot detect branch-level divergence.

Content hash per artifact is NOT required (git diff against indexed commit is sufficient for the detector pattern).

### Layer 2: lib/freshness.py

New module in `scripts/lib/`. Used internally by all scripts. Stdlib only.

**GitState**: Takes `repo_path` and `indexed_commit` (from backend metadata), provides branch, HEAD commit, divergent files, and **divergence direction**. Uses `git diff -z --name-only <indexed_commit>` as the primary detection mechanism (single command, safe path handling). Lazy-evaluated, cached per script invocation.

**Two-strategy fallback** (exact-or-degraded):
1. **Exact**: indexed commit exists locally → precise diff + direction detection via `merge-base --is-ancestor`
2. **Degraded**: indexed commit not found → only uncommitted changes + repo-level warning

Strategy 2 from v2 (`origin/<branch>` as surrogate) was removed — under FPF B.5.2, if discriminating evidence is unavailable, the honest state is "degraded," not fake precision.

```python
class GitState:
    """Local git repository state snapshot. Stdlib only."""

    def __init__(self, repo_path: str, indexed_commit: str = None,
                 indexed_branch: str = None):
        self.repo_path = repo_path
        self.indexed_commit = indexed_commit
        self.indexed_branch = indexed_branch
        self.branch = self._git("rev-parse", "--abbrev-ref", "HEAD")
        self.head_commit = self._git("rev-parse", "--short", "HEAD")
        self._divergent = None
        self._untracked = None
        self._direction = None
        self._diff_failed = False

    @property
    def branch_matches(self) -> bool:
        """Whether local branch matches the indexed branch."""
        if not self.indexed_branch:
            return True  # unknown → assume match
        return self.branch == self.indexed_branch

    @property
    def divergence_direction(self) -> str:
        """Relationship between local state and indexed state.
        Returns: 'exact', 'local_ahead', 'local_behind', 'diverged', 'unknown'."""
        if self._direction is None:
            self._direction = self._compute_direction()
        return self._direction

    def _compute_direction(self) -> str:
        if self._diff_failed or not self.indexed_commit:
            return "unknown"
        if not self.divergent_files:
            return "exact"
        # Is indexed_commit ancestor of HEAD? → local has moved ahead
        if self._git("merge-base", "--is-ancestor",
                      self.indexed_commit, "HEAD") is not None:
            return "local_ahead"
        # Is HEAD ancestor of indexed_commit? → local is behind
        if self._git("merge-base", "--is-ancestor",
                      "HEAD", self.indexed_commit) is not None:
            return "local_behind"
        return "diverged"

    @property
    def divergent_files(self) -> set[str]:
        """All files that differ between indexed state and local working tree.
        Covers: branch differences, committed, staged, and unstaged changes."""
        if self._divergent is None:
            self._divergent = self._compute_divergent()
        return self._divergent

    def _compute_divergent(self) -> set[str]:
        # Strategy 1: diff working tree against indexed commit (precise)
        # Single command captures committed + staged + unstaged changes
        if self.indexed_commit:
            out = self._git("diff", "-z", "--name-only", self.indexed_commit)
            if out is not None:
                return set(f for f in out.split("\0") if f) if out else set()
            # Indexed commit not in local history — degrade

        # Strategy 2: only uncommitted changes (degraded — last resort)
        self._diff_failed = True
        out = self._git("diff", "-z", "--name-only", "HEAD") or ""
        return set(f for f in out.split("\0") if f)

    @property
    def untracked_files(self) -> set[str]:
        if self._untracked is None:
            out = self._git("ls-files", "-z", "--others", "--exclude-standard")
            self._untracked = set(f for f in out.split("\0") if f) if out else set()
        return self._untracked

    def file_status(self, rel_path: str) -> str:
        """Returns: 'fresh', 'modified', 'deleted', or 'missing'.
        Uses suffix matching to handle monorepo path offsets."""
        is_divergent = any(
            df == rel_path or df.endswith("/" + rel_path)
            for df in self.divergent_files
        )
        if is_divergent:
            full = os.path.join(self.repo_path, rel_path)
            if not os.path.exists(full):
                return "deleted"
            return "modified"
        full = os.path.join(self.repo_path, rel_path)
        if not os.path.exists(full):
            return "missing"  # exists in cloud but not locally
        return "fresh"

    @property
    def freshness_warning(self) -> str | None:
        """Warning when diff precision is degraded."""
        if self._diff_failed:
            return ("Freshness detection limited: indexed commit not found locally. "
                    "Only uncommitted changes are detected. "
                    "Run 'git fetch' to get full freshness precision.")
        return None

    def _git(self, *args) -> str | None:
        """Run git command. Returns stdout on success, None on failure."""
        result = subprocess.run(
            ["git", "-C", self.repo_path] + list(args),
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
```

**`--repo-path` argument parsing** (shared across scripts):

```python
def parse_repo_path(argv: list[str]) -> tuple[str | None, list[str]]:
    """Extract --repo-path from argv. Returns (repo_path, remaining_args).

    Errors with clear message if --repo-path is not provided.
    """
    repo_path = None
    remaining = []
    i = 0
    while i < len(argv):
        if argv[i] == "--repo-path" and i + 1 < len(argv):
            value = argv[i + 1]
            repo_path = None if value.lower() == "none" else value
            i += 2
        else:
            remaining.append(argv[i])
            i += 1

    if "--repo-path" not in argv:
        print(
            "Error: --repo-path is required.\n\n"
            "Pass the local path to the repository you are working with:\n"
            "  python search.py \"query\" my-repo --repo-path /path/to/repo\n\n"
            "If the repository is not available locally:\n"
            "  python search.py \"query\" external-repo --repo-path none\n\n"
            "Why: --repo-path enables freshness detection. Without it, the script\n"
            "cannot check whether cloud index data matches your local files.\n"
            "Please retry with --repo-path.",
            file=sys.stderr
        )
        sys.exit(1)

    return repo_path, remaining
```

### Layer 3: Script Behavior

#### search.py

Cloud search results are annotated based on local git state and **divergence direction**:

- **Fresh files**: returned as-is (no annotation)
- **Modified files (local_ahead or diverged)**: result shown with `!! MODIFIED LOCALLY` marker + instruction to Read() entire file (no line ranges — they are stale)
- **Modified files (local_behind)**: result shown with cloud data + note to `git pull`
- **Deleted files**: filtered from results, counted in summary
- **Direction + branch header**: one-line header with direction and branch info
- **Summary footer**: counts of fresh/modified/filtered results + untracked file count

Example output (local_ahead):

```
Local is AHEAD of cloud index (indexed: abc123d on main | local: feature/auth-refactor)

--- Result #1 [Symbol] ---
  File: src/auth.py:45-67
  Symbol: AuthService.validate_token
  Source: my-backend
  Description: Validates JWT tokens against the configured secret...
  !! MODIFIED LOCALLY — Read() the entire file to get current content (do NOT use line ranges, they are stale)

--- Result #2 [Chunk] ---
  File: src/utils.py:12-30
  Source: my-backend
  Description: Helper functions for string formatting...

(2 results | 1 modified locally — Read() entire file | 1 filtered: deleted locally | 3 new local files not in index)
```

Example output (local_behind):

```
Local is BEHIND cloud index — consider running 'git pull' (indexed: abc123d on main | local: main)

--- Result #1 [Symbol] ---
  File: src/auth.py:45-67
  ...
  Note: cloud index is newer than local. Cloud data shown; local file may be outdated.

(2 results | 1 has newer cloud version | run 'git pull' for latest)
```

#### fetch.py

The most significant behavior change. Behavior depends on **divergence direction**:

- **Direction header**: one-line header before any artifacts (Serial Position Effect — primacy):

```
Local is AHEAD of cloud index (indexed: abc123d on main | local: feature/auth-refactor)
```

- **Fresh file**: return cloud content as before (with line numbers)

- **Modified file + `local_ahead` or `diverged`**: do NOT return cloud content (it's stale). Output a redirect. **Explicitly forbids line ranges** — LLMs will literally use stale line numbers unless told not to:

```
============================================================
!! src/auth.py — MODIFIED LOCALLY (local is ahead of cloud index)
============================================================
This file has been modified since the cloud index was built.
Cloud index had: src/auth.py (AuthService.validate_token, was at lines 45-67)
>> Read() the ENTIRE file to get current content.
>> Do NOT use start_line/end_line — line numbers have shifted.
>> To find the symbol, search for "AuthService.validate_token" in the file.
```

- **Modified file + `local_behind`**: return cloud content (cloud is newer) with note:

```
============================================================
src/auth.py — cloud index is NEWER than local (run 'git pull')
============================================================
[cloud content with line numbers — these are authoritative]
```

- **Modified file + `unknown` (degraded)**: return cloud content with caveat:

```
============================================================
src/auth.py — DIVERGENCE DETECTED (precision degraded)
============================================================
[cloud content with line numbers]
Note: Freshness detection is limited. Consider Read() to verify.
```

- **Deleted file**: skip with note in summary
- **Missing file**: return cloud content with note: `(cloud index only — not found locally)`
- **`--repo-path none`**: return cloud content for everything (normal behavior)

Summary footer:

```
(3 artifacts | 1 from cloud | 1 modified — Read() entire file | 1 skipped: deleted)
```

#### chat.py

- Direction + branch note prepended: `Note: Local is ahead of cloud index (indexed: abc123d on main, local: feature/auth-refactor).`
- Repo-level freshness caveat: `Note: N files differ between local and cloud index. Answer may reference outdated code.`
- No per-file freshness (backend doesn't return which files were referenced in the answer — no citation surface)

#### explore.py — Removed

explore.py was removed from the skill. The agent is a better orchestrator than a hardcoded Python pipeline: it can inspect search results, apply freshness annotations, Read() modified files, and decide whether to invoke chat.py — all with reasoning between steps.

### Layer 4: SKILL.md Updates

The SKILL.md instructs the agent to always pass `--repo-path`:

```markdown
### Local Repository Context (required)

All scripts require `--repo-path` to enable freshness detection:

    python scripts/search.py "auth" my-backend --repo-path /path/to/repo
    python scripts/fetch.py "org/repo::src/auth.py" --repo-path /path/to/repo

If the repository is not available locally:

    python scripts/search.py "auth" external-lib --repo-path none

The scripts will automatically:
- Detect divergence direction (local ahead / behind / diverged)
- Mark results from locally modified files
- Filter out files that were deleted locally
- Note when the cloud index is on a different branch
- Report count of new local files not in the cloud index

When a result is marked as "MODIFIED LOCALLY" and local is ahead:
1. The cloud data (description, line numbers) is outdated
2. Use Read() to get the ENTIRE current file — do NOT use start_line/end_line
3. To find a specific symbol, search for it by name in the file

When the script says "cloud index is NEWER than local":
1. The cloud data is more recent — use it as-is
2. Consider running 'git pull' to sync your local copy
```

### Backward Compatibility

`--repo-path` is mandatory in v2. Scripts without it return a clear error with usage instructions. This is a breaking change from v1 behavior, but:

- The error message is self-documenting — agents recover on first retry
- `--repo-path none` preserves pure cloud-only behavior
- Backend changes (indexing metadata) are additive — old clients ignore new fields
- The SKILL.md update teaches agents the new contract immediately

### Edge Cases

| Case | Handling |
|---|---|
| **Monorepo** | `--repo-path` points to git root; `file_status()` uses suffix matching to handle subdir path offsets |
| **Submodules** | Treated as part of parent repo's git state; submodule-internal changes detected by parent's `git diff` |
| **Symlinks** | `os.path.exists()` follows symlinks; no special handling needed |
| **Binary files** | Git status still works; fetch.py returns cloud content (binary files are unlikely search results) |
| **Permission errors** | `file_status()` returns "missing" on read error; not conflated with "deleted" |
| **Large repos** | `git diff -z --name-only` is fast even for large repos; no file content reading |
| **Indexed commit not in local history** | Degraded mode: only uncommitted changes detected. Warning emitted. Direction = "unknown" |
| **Shallow clone (`--depth 1`)** | Indexed commit absent → same degraded mode as above. Explicit warning to `git fetch --unshallow` |
| **Local behind indexed commit** | Direction = "local_behind" → cloud data is newer, serve as-is with note to `git pull` |
| **Multiple data sources** | `--repo-path` matched against artifact's repo prefix via suffix matching; unmatched artifacts use cloud data |
| **Network-less environment** | Cloud API call fails; git state check still works; graceful error |
| **TOCTOU (file changes between check and agent Read)** | Acceptable: agent's Read() gets the latest state; our check was a best-effort signal |
| **Forked remote** | Direction detection via `merge-base` still works if indexed commit exists locally; otherwise degraded mode |

## Implementation Plan

| Phase | Scope | Dependencies |
|---|---|---|
| **0a. Backend: indexing metadata** | Return `indexing.commit`, `indexing.branch`, `indexing.indexedAt` per data source in API responses | None |
| **0b. Remove explore.py** | Remove explore.py — agent orchestrates search+chat workflow itself | None |
| **1. lib/freshness.py** | New module: GitState (with `indexed_commit` support, direction detection, suffix matching), `parse_repo_path`, file status logic | Phase 0a |
| **2. fetch.py** | Add mandatory `--repo-path`, redirect for modified files, filter deleted | Phase 1 |
| **3. search.py** | Add mandatory `--repo-path`, annotate modified, filter deleted, summary | Phase 1 |
| **4. chat.py** | Add `--repo-path` passthrough, branch/modified notes | Phase 1 |
| **5. SKILL.md** | Update documentation with `--repo-path` usage and freshness behavior | Phase 2-4 |

Backend metadata (Phase 0a) is a **prerequisite**, not an independent phase. Without `indexing.commit`, `git diff` can only detect uncommitted changes — branch-level divergence and direction are invisible. The two-strategy fallback in GitState (exact with direction detection → degraded with warning) provides honest degradation, but full precision requires the backend to return the indexed commit.

### What is NOT in scope

- **Content hashing** (h5/adler32/blake2s): Not needed. `git diff <indexed_commit>` is sufficient when the skill is a detector, not a deliverer. May be reconsidered later as optimization to reduce false positives (flagging unchanged artifacts in modified files).
- **Local file reading by scripts**: Eliminated. The agent reads local files itself via Read().
- **Local overlay search for new files**: Deferred. Script reports untracked file count; actual search requires local indexing infrastructure.
- **chat.py deep freshness**: Deferred. Requires backend support for local context in RAG pipeline.
- **freshness.py diagnostic script**: Dropped. Freshness information is now inline in every script's output.

## Appendix: FPF Traceability

| Design decision | FPF pattern | How it applies |
|---|---|---|
| Cloud data is perishable | B.3.4 Evidence Decay | `valid_until` = indexed commit; data accrues epistemic debt as local diverges |
| Per-file reliability assessment | B.3 F-G-R Trust Calculus | R computed per artifact based on git file status |
| Mandatory `--repo-path` | B.3 WLNK (Weakest Link) | Optional parameter = weakest link in trust chain; making it mandatory removes the link |
| Summary signals incompleteness | B.3 WLNK | Even one stale result means the search set may be incomplete |
| Separate detection from resolution | B.5.2 Abductive Loop → Scope discipline | Skill's scope = detection; agent's scope = resolution. Mixing them causes line drift bug. |
| Governance: Refresh/Deprecate/Waive | B.3.4 Governance Loop | Refresh = agent Read(); Deprecate = filter deleted; Waive = `--repo-path none` |
| Five candidates evaluated | B.5.2 Abductive Loop | Rival set preserved; prime hypothesis (F) selected via plausibility filters |
| v2 supersedes v1 after external review | B.5.2 Reopening | New evidence (Codex/Gemini findings) triggered reopening; v1 candidate (E) demoted, v2 candidate (F) selected |
| Branch header on all scripts | UX: Serial Position Effect | Primacy + recency: severe signal appears first AND last in output |
| Zero annotation for fresh results | UX: Cognitive Load | Extraneous load = 0 for unchanged files; cost only where intrinsic |
| Variant B (dataSources array) | UX: Chunking / Cognitive Load | Group related metadata once instead of scattering across results |
| `!! MODIFIED` prefix format | UX: Von Restorff Effect | Distinct marker breaks uniform pattern, ensuring stale items are noticed |
| Error message with examples | UX: Error Handling best practices | `[What's wrong] + [How to fix it]` maximizes first-retry recovery |
| Divergence direction detection | B.3 F-G-R Trust Calculus | R depends not only on whether files differ, but on which side is authoritative. Direction = authority signal |
| Remove Strategy 2 (origin/branch) | B.5.2 Abductive Loop → Defer | When discriminating evidence is unavailable, honest answer is "degraded," not surrogate precision |
| Search completeness as G problem | B.3 ClaimScope (G) | Missing files (new on branch, renamed) reduce search scope; WLNK on G means result set is incomplete |
| Repo-path↔datasource matching | B.3 Congruence Level (CL) | Suffix matching raises CL from "weak guess" toward "plausible mapping"; explicit binding would reach CL2 |
| Forbid stale line ranges for agent | UX: Agent Psychology | LLMs are literal — operational constraints ("do NOT use line ranges") work better than soft warnings ("approximate") |
| Suffix path matching in file_status | B.3 CL + Operational robustness | Absorbs monorepo path offsets; prevents silent false-negative on divergence check |
