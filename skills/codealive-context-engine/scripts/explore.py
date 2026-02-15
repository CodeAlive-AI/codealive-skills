#!/usr/bin/env python3
"""
CodeAlive Explorer - Smart code exploration workflow

Combines search and consultation for intelligent code discovery.
Automatically decides when to search vs ask, when to go deep, and how to progressively narrow results.

Usage:
    python explore.py "understand authentication" my-backend
    python explore.py "dependency:lodash debounce usage" --workspace platform-team
    python explore.py "pattern:error handling across microservices" service-*

Modes:
    - understand:<topic>       → Search + consultant explanation
    - dependency:<lib>         → Deep-dive into library usage and internals
    - pattern:<pattern>        → Find pattern implementations across projects
    - implement:<feature>      → Find similar features to guide implementation
    - debug:<symptom>          → Trace from symptom to root cause

Examples:
    # Understand a feature
    python explore.py "understand:user authentication" my-backend

    # Learn how a dependency works
    python explore.py "dependency:axios interceptors" my-frontend

    # Find patterns across organization
    python explore.py "pattern:error handling" workspace:backend-team

    # Plan new feature implementation
    python explore.py "implement:rate limiting" workspace:all-services

    # Debug an issue
    python explore.py "debug:slow database queries" my-api-service
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def parse_query(query: str) -> Tuple[str, str]:
    """
    Parse query to extract mode and actual query.

    Returns:
        (mode, query) tuple
    """
    modes = ["understand", "dependency", "pattern", "implement", "debug"]

    for mode in modes:
        prefix = f"{mode}:"
        if query.lower().startswith(prefix):
            return mode, query[len(prefix):].strip()

    # Default to understand mode
    return "understand", query


def explore_understand(client: CodeAliveClient, query: str, data_sources: List[str]) -> None:
    """Understand a topic: Search first, then ask consultant to explain."""
    print(f"🎯 Mode: UNDERSTAND")
    print(f"📝 Topic: {query}")
    print(f"📚 Data sources: {', '.join(data_sources)}")
    print()

    # Step 1: Search for relevant code
    print("🔍 Step 1: Searching for relevant code...")
    print()

    search_results = client.search(
        query=query,
        data_sources=data_sources,
        mode="auto",
        include_content=False
    )

    # Show top results
    print("📍 Found relevant locations:")
    items = search_results if isinstance(search_results, list) else search_results.get("results", []) if isinstance(search_results, dict) else []
    for idx, result in enumerate(items[:5], 1):
        location = result.get("location", {})
        file_path = location.get("path") or result.get("filePath") or result.get("file") or "Unknown"
        range_info = location.get("range", {})
        line = range_info.get("start", {}).get("line") or result.get("startLine") or "?"
        print(f"   {idx}. {file_path}:{line}")
    print()

    # Step 2: Ask consultant to explain
    print("💬 Step 2: Getting expert explanation...")
    print()

    consultant_query = f"Based on the search results for '{query}', explain how this works in the codebase. Focus on architecture, key components, and data flow."

    chat_result = client.chat(
        question=consultant_query,
        data_sources=data_sources
    )

    print("="*80)
    print("📖 EXPLANATION:")
    print("="*80)
    print(chat_result["answer"])
    print("="*80)


def explore_dependency(client: CodeAliveClient, query: str, data_sources: List[str]) -> None:
    """Deep-dive into a library or dependency."""
    print(f"🎯 Mode: DEPENDENCY DEEP-DIVE")
    print(f"📦 Library: {query}")
    print(f"📚 Data sources: {', '.join(data_sources)}")
    print()

    # Search for usage patterns
    print("🔍 Step 1: Finding usage patterns...")
    print()

    usage_query = f"How is {query} used? Show me import statements and usage examples"
    search_results = client.search(
        query=usage_query,
        data_sources=data_sources,
        mode="auto",
        include_content=True
    )

    # Ask consultant about internals and best practices
    print("💬 Step 2: Understanding internals and best practices...")
    print()

    consultant_query = f"""About the library/dependency '{query}':
1. How does it work internally?
2. What are the common usage patterns in this codebase?
3. What are best practices and potential gotchas?
4. How do other projects in the ecosystem use it?"""

    chat_result = client.chat(
        question=consultant_query,
        data_sources=data_sources
    )

    print("="*80)
    print("📖 DEPENDENCY ANALYSIS:")
    print("="*80)
    print(chat_result["answer"])
    print("="*80)


def explore_pattern(client: CodeAliveClient, query: str, data_sources: List[str]) -> None:
    """Find pattern implementations across projects."""
    print(f"🎯 Mode: PATTERN DISCOVERY")
    print(f"🔍 Pattern: {query}")
    print(f"📚 Data sources: {', '.join(data_sources)}")
    print()

    # Use deep search for cross-project patterns
    print("🔍 Searching across projects (deep mode)...")
    print()

    search_results = client.search(
        query=f"Show me different implementations of {query}",
        data_sources=data_sources,
        mode="deep",
        include_content=True
    )

    # Ask consultant to analyze and compare
    print("💬 Analyzing patterns...")
    print()

    consultant_query = f"""Analyze the different implementations of '{query}' found in the codebase:
1. What are the common patterns?
2. What are the variations?
3. Which approach is recommended and why?
4. Are there any anti-patterns to avoid?"""

    chat_result = client.chat(
        question=consultant_query,
        data_sources=data_sources
    )

    print("="*80)
    print("📊 PATTERN ANALYSIS:")
    print("="*80)
    print(chat_result["answer"])
    print("="*80)


def explore_implement(client: CodeAliveClient, query: str, data_sources: List[str]) -> None:
    """Find similar features to guide new implementation."""
    print(f"🎯 Mode: IMPLEMENTATION GUIDE")
    print(f"✨ Feature to implement: {query}")
    print(f"📚 Data sources: {', '.join(data_sources)}")
    print()

    # Search for similar features
    print("🔍 Step 1: Finding similar implementations...")
    print()

    search_results = client.search(
        query=f"Similar features to {query}, existing implementations",
        data_sources=data_sources,
        mode="auto",
        include_content=False
    )

    # Ask consultant for implementation guidance
    print("💬 Step 2: Getting implementation guidance...")
    print()

    consultant_query = f"""I need to implement '{query}'. Based on the codebase:
1. What similar features exist that I can learn from?
2. What are the architectural patterns I should follow?
3. What components/services do I need to integrate with?
4. What are the key considerations (security, performance, testing)?
5. What's the recommended approach to implement this?"""

    chat_result = client.chat(
        question=consultant_query,
        data_sources=data_sources
    )

    print("="*80)
    print("🛠️  IMPLEMENTATION GUIDE:")
    print("="*80)
    print(chat_result["answer"])
    print("="*80)


def explore_debug(client: CodeAliveClient, query: str, data_sources: List[str]) -> None:
    """Trace from symptom to root cause."""
    print(f"🎯 Mode: DEBUG INVESTIGATION")
    print(f"🐛 Issue: {query}")
    print(f"📚 Data sources: {', '.join(data_sources)}")
    print()

    # Search for related code
    print("🔍 Step 1: Finding related code...")
    print()

    search_results = client.search(
        query=f"Code related to {query}",
        data_sources=data_sources,
        mode="auto",
        include_content=True
    )

    # Ask consultant to analyze
    print("💬 Step 2: Analyzing root cause...")
    print()

    consultant_query = f"""Help me debug: '{query}'
1. What code is likely involved?
2. What could be causing this issue?
3. What should I check first?
4. What are common mistakes related to this?
5. How can I trace and fix this issue?"""

    chat_result = client.chat(
        question=consultant_query,
        data_sources=data_sources
    )

    print("="*80)
    print("🔧 DEBUG ANALYSIS:")
    print("="*80)
    print(chat_result["answer"])
    print("="*80)


def main():
    """CLI interface for smart code exploration."""
    if len(sys.argv) < 3:
        print("Error: Missing required arguments.", file=sys.stderr)
        print("Usage: python explore.py <mode:query> <data_source> [data_source2...]", file=sys.stderr)
        print("Modes: understand, dependency, pattern, implement, debug", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--help":
        print(__doc__)
        sys.exit(0)

    query = sys.argv[1]
    data_sources = []

    # Parse arguments
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--workspace" and i + 1 < len(sys.argv):
            # Add workspace prefix
            data_sources.append(f"workspace:{sys.argv[i + 1]}")
            i += 2
        else:
            data_sources.append(arg)
            i += 1

    if not data_sources:
        print("Error: At least one data source is required. Run datasources.py to see available sources.", file=sys.stderr)
        sys.exit(1)

    try:
        client = CodeAliveClient()
        mode, actual_query = parse_query(query)

        print("\n" + "="*80)
        print("🚀 CodeAlive Explorer")
        print("="*80 + "\n")

        if mode == "understand":
            explore_understand(client, actual_query, data_sources)
        elif mode == "dependency":
            explore_dependency(client, actual_query, data_sources)
        elif mode == "pattern":
            explore_pattern(client, actual_query, data_sources)
        elif mode == "implement":
            explore_implement(client, actual_query, data_sources)
        elif mode == "debug":
            explore_debug(client, actual_query, data_sources)

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
