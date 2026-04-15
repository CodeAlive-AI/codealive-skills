# CodeAlive Workflows

Complete workflows for common code exploration scenarios using CodeAlive.

## Table of Contents
- [Initial Codebase Exploration](#initial-codebase-exploration)
- [Understanding Existing Features](#understanding-existing-features)
- [Planning New Features](#planning-new-features)
- [Dependency Deep-Dive](#dependency-deep-dive)
- [Cross-Project Pattern Discovery](#cross-project-pattern-discovery)
- [Debugging & Investigation](#debugging--investigation)
- [Technology Evaluation](#technology-evaluation)
- [Onboarding to New Codebases](#onboarding-to-new-codebases)

---

## Initial Codebase Exploration

**Goal:** Build a mental model of an unknown codebase

### Step 1: Discover Available Code
```bash
python datasources.py
```

Review output to understand:
- What repositories are indexed
- What workspaces group related repos
- Which data sources to use for exploration

### Step 2: Understand Entry Points
```bash
python search.py "main application entry point, startup initialization" my-backend-repo
```

### Step 3: Explore Key Features
```bash
python search.py "main features, core capabilities, major services" my-backend-repo
```

### Step 4: Fetch and Inspect Key Artifacts
```bash
# Fetch full source for the most relevant search results
python fetch.py "my-org/backend::src/app.py::main()"

# Trace relationships to understand dependencies
python relationships.py "my-org/backend::src/app.py::main()" --profile allRelevant
```

### Step 5: Understand Data Models
```bash
python search.py "database models, schemas, entity definitions" my-backend-repo
```

**Progressive Discovery:**
- Start with broad architectural questions
- Narrow to specific components
- Drill into implementation details

---

## Understanding Existing Features

**Goal:** Trace a feature implementation across all layers

### Example: Understanding User Authentication

#### Step 1: Start with Search
```bash
python search.py "user authentication, login flow, session management" my-backend
python grep.py "refresh token" my-backend
```

#### Step 2: Fetch Full Source for Top Results
```bash
# Load actual source for the most relevant identifiers from Step 1
python fetch.py "my-org/backend::src/auth/handler.py::login()"
```

#### Step 3: Trace Through Layers
```bash
# API Layer
python search.py "login controller, authentication route handler" my-backend

# Service Layer
python search.py "authentication service, user validation logic" my-backend

# Database Layer
python search.py "user model, credentials storage" my-backend
```

#### Step 4: Trace Relationships
```bash
# Understand what the auth handler calls and who calls it
python relationships.py "my-org/backend::src/auth/handler.py::login()" --profile allRelevant
```

#### Step 5: Find Related Features
```bash
python search.py "password reset, email verification, 2FA" my-backend
```

**Pattern:** API → Service → Repository/Database → Related Features

---

## Planning New Features

**Goal:** Find patterns and integration points before implementing

### Example: Adding Rate Limiting

#### Step 1: Check for Existing Similar Features
```bash
python search.py "rate limiting, request throttling, API quotas" my-backend workspace:all-backend
```

#### Step 2: Understand Middleware Patterns
```bash
python search.py "middleware patterns, cross-cutting concerns, logging, authentication" my-backend
python fetch.py "my-org/backend::src/middleware/auth.py::AuthMiddleware"
```

#### Step 3: Find Integration Points
```bash
python search.py "middleware registration, request pipeline configuration" my-backend
```

#### Step 4: Check Dependencies
```bash
python search.py "express-rate-limit, rate-limiter-flexible, existing rate limiting libraries" workspace:all-backend
```

#### Step 5: Trace Integration Points
```bash
# Understand how existing middleware integrates
python relationships.py "my-org/backend::src/middleware/auth.py::AuthMiddleware" --profile callsOnly
```

**Output:** Clear picture of middleware patterns, integration points, and file locations

---

## Dependency Deep-Dive

**Goal:** Understand how a library works and how it's used

### Example: Understanding axios Usage

#### Step 1: Find All Usage
```bash
python grep.py "axios" my-frontend --ext .ts --ext .js
python search.py "axios usage patterns, HTTP client configuration" my-frontend
```

#### Step 2: Understand Configuration
```bash
python search.py "axios configuration, base URL, default headers, interceptors" my-frontend
```

#### Step 3: Learn Internal Implementation
```bash
# Fetch the actual interceptor implementation (requires axios to be indexed)
python search.py "interceptor mechanism implementation" axios-library
python fetch.py "axios::lib/core/Axios.js::Axios.request()"
```

#### Step 4: Find Best Practices
```bash
python search.py "axios best practices, error handling, retry" my-frontend
python fetch.py "my-org/frontend::src/api/client.ts::createApiClient()"
```

#### Step 5: Compare with Alternatives
```bash
python search.py "fetch API, got, node-fetch, HTTP client libraries" workspace:all-frontend
python grep.py "import.*fetch\\|require.*fetch" workspace:all-frontend --regex
```

**Use Case:** Replace MCP-based online documentation with real usage examples

---

## Cross-Project Pattern Discovery

**Goal:** Learn patterns from across your organization

### Example: Error Handling Patterns

#### Step 1: Broad Search Across Workspace
```bash
python search.py "error handling patterns, exception middleware, error logging" workspace:backend-team
```

#### Step 2: Find Concrete Implementations
```bash
python grep.py "catch|ExceptionHandler|ErrorMiddleware" workspace:backend-team --regex
python fetch.py "org/service-a::src/middleware/error.py::ErrorMiddleware"
python fetch.py "org/service-b::src/errors/handler.ts::handleError()"
```

#### Step 3: Compare Patterns via Relationships
```bash
# Understand how error handlers integrate with the rest of the codebase
python relationships.py "org/service-a::src/middleware/error.py::ErrorMiddleware" --profile callsOnly
python relationships.py "org/service-b::src/errors/handler.ts::handleError()" --profile callsOnly
```

#### Step 4: Identify Anti-Patterns
```bash
# Search for common mistakes
python grep.py "except:$|catch\\s*\\{\\}" workspace:backend-team --regex
python search.py "swallowed exceptions, empty catch blocks, error suppression" workspace:backend-team
```

**Output:** Pattern comparison with real source code evidence and relationship context

---

## Debugging & Investigation

**Goal:** Trace from symptom to root cause

### Example: Investigating Slow API Responses

#### Step 1: Find Related Code
```bash
python search.py "API performance, slow queries, request handling" my-api-service
```

#### Step 2: Investigate Database Queries
```bash
python search.py "database queries, ORM operations, N+1 problem" my-api-service
```

#### Step 3: Fetch and Trace Suspicious Code
```bash
# Fetch the actual query implementations
python fetch.py "my-org/api::src/db/queries.py::get_user_data()"
# Trace what calls this query and what it calls
python relationships.py "my-org/api::src/db/queries.py::get_user_data()" --profile callsOnly
```

#### Step 4: Find Monitoring/Logging
```bash
python search.py "performance logging, request timing, profiling" my-api-service
python grep.py "slow_query|performance|latency" my-api-service --regex
```

**Pattern:** Symptom → Search → Fetch source → Trace relationships → Identify bottleneck

---

## Technology Evaluation

**Goal:** Compare technologies by seeing real usage

### Example: Choosing a State Management Library

#### Step 1: Find Existing Usage
```bash
python grep.py "Redux|MobX|Zustand|useContext" workspace:all-frontend --regex
python search.py "state management patterns, store configuration" workspace:all-frontend
```

#### Step 2: Fetch and Compare Implementations
```bash
# Fetch the actual store/state implementations from different projects
python fetch.py "org/app-a::src/store/index.ts::configureStore()"
python fetch.py "org/app-b::src/state/context.tsx::AppProvider"
```

#### Step 3: Check Performance Patterns
```bash
python search.py "state management performance, re-render optimization, memoization" workspace:all-frontend
python grep.py "useMemo|useCallback|React.memo" workspace:all-frontend --regex
```

**Output:** Data-driven technology comparison based on real source code from your projects

---

## Onboarding to New Codebases

**Goal:** Quickly understand an unfamiliar project

### Day 1: Get Overview

```bash
# Discover what's indexed
python datasources.py

# Find entry points and main features
python search.py "main application entry point, startup initialization" new-service
python search.py "main features, core capabilities, major services" new-service

# Understand the tech stack
python grep.py "package.json|requirements.txt|go.mod" new-service --regex
python fetch.py "my-org/new-service::package.json"
```

### Day 2: Understand Core Features

```bash
# Find key components
python search.py "core services, main controllers, important modules" new-service

# Fetch and read the main entry points
python fetch.py "my-org/new-service::src/app.py::create_app()"

# Trace data flow through relationships
python relationships.py "my-org/new-service::src/app.py::create_app()" --profile callsOnly
```

### Day 3: Learn Development Practices

```bash
# Testing patterns
python search.py "test files, testing patterns, test setup" new-service

# Configuration
python search.py "configuration, environment variables, settings" new-service

# Deployment
python search.py "deployment configuration, CI/CD, build process" new-service
```

### Week 1: Deep Dive

```bash
# Feature-by-feature exploration
python search.py "user management" new-service
python search.py "API integration" new-service
python search.py "background jobs" new-service

# Fetch source for key features and trace their dependencies
python fetch.py "my-org/new-service::src/users/service.py::UserService"
python relationships.py "my-org/new-service::src/users/service.py::UserService" --profile allRelevant
```

**Progressive Learning:** Overview → Core Features → Development Practices → Deep Dives

---

## Pro Tips

### Workspace vs Repository
- **Repository:** Targeted, specific search
- **Workspace:** Broad, cross-project patterns

```bash
# Specific
python search.py "auth logic" my-backend-api

# Broad
python search.py "authentication patterns" workspace:all-backend
```

### Choosing search.py vs grep.py
- **Concepts and behavior** ("authentication middleware") → `search.py`
- **Exact text or regex** ("AuthService", "TODO: fix") → `grep.py`
- **Not sure?** Start with `search.py`, switch to `grep.py` if you learn specific names

### Getting Full Source
- **Current repo:** use your editor's file-read tool on the path shown in results
- **External repos:** `python fetch.py <identifier>` — the identifier comes from search results

### Combine with Local Tools
```bash
# CodeAlive for discovery
python search.py "payment processing" my-backend

# Fetch full source for relevant results
python fetch.py "my-org/backend::src/payments/processor.py::PaymentProcessor"

# Trace call graph
python relationships.py "my-org/backend::src/payments/processor.py::PaymentProcessor" --profile callsOnly

# Read local files for current working repo
# Use editor's Read tool for files in your working directory
```

### `description` is a triage pointer, not the source of truth
`search.py` returns a `description` for every result. Use it ONLY to decide
*which* artifacts deserve a closer look — never as the basis for your
understanding of the code. For each relevant result, immediately load the real
source via `fetch.py <identifier>` (external repos) or your editor's file-read
tool (current working repo). Treat only that real `content` as ground truth.

### Drill into relationships when you need the call graph
Once you've located an artifact via `search.py` or fetched it via `fetch.py`,
use `relationships.py` to expand it:
```bash
# Default: full outgoing + incoming call graph
python relationships.py "my-org/backend::src/auth.py::AuthService.login()"

# Class hierarchy
python relationships.py "my-org/backend::src/models.py::User" --profile inheritanceOnly

# Everything (calls + inheritance), bigger cap
python relationships.py "my-org/backend::src/svc.py::Service" --profile allRelevant --max-count 200
```
The `fetch.py` response shows up to 3 calls per direction as a preview;
`relationships.py` is how you escape that preview cap and switch profiles.

### Iterative Refinement
Start broad → Review results → Refine query → Repeat

```
1. "authentication" → Too many results
2. "JWT authentication implementation" → Better
3. "JWT token validation middleware" → Specific
```
