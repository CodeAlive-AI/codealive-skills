#!/usr/bin/env python3
"""
CodeAlive Consultant - AI-powered codebase Q&A

Ask questions about code architecture, implementation details, patterns, and best practices.
Works across your entire indexed codebase ecosystem.

Usage:
    python chat.py "How does authentication work?" my-repo
    python chat.py "Explain the database schema" workspace:backend-team
    python chat.py "What's the best way to add caching? Prior context: ..." my-repo

Examples:
    # Ask about current project
    python chat.py "How is user authentication implemented?" my-backend

    # Ask across multiple repos
    python chat.py "How do services communicate?" service-a service-b

    # Ask about dependencies/libraries
    python chat.py "How does lodash debounce work internally?" lodash

    # v3 chat is stateless: include prior findings and constraints in every question.
    python chat.py "Given prior finding X, what about error handling?" my-backend

    # Cross-project learning
    python chat.py "Show me authentication patterns across our org" workspace:all-backend
"""

import sys
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def main():
    """CLI interface for codebase consultant."""
    if len(sys.argv) < 2:
        print("Error: Missing required arguments.", file=sys.stderr)
        print("Usage: python chat.py <question> <data_source> [data_source2...]", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--help":
        print(__doc__)
        sys.exit(0)

    question = sys.argv[1]
    data_sources = []

    # Parse arguments
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in {"--continue", "--conversation-id"}:
            print("Error: chat is stateless in v3; include prior context in the question instead.", file=sys.stderr)
            sys.exit(1)
        else:
            data_sources.append(arg)
            i += 1

    if not data_sources:
        print("Error: At least one data source is required.", file=sys.stderr)
        print("Run datasources.py to see available sources.", file=sys.stderr)
        sys.exit(1)

    try:
        client = CodeAliveClient()

        print(f"💬 Question: {question}", file=sys.stderr)
        print(f"📚 Analyzing: {', '.join(data_sources)}", file=sys.stderr)
        print("ℹ️  v3 chat is stateless; each question must include needed prior context.", file=sys.stderr)
        print(file=sys.stderr)
        print("🤔 Thinking...", file=sys.stderr)
        print(file=sys.stderr)

        result = client.chat(
            question=question,
            data_sources=data_sources,
        )

        print("="*80)
        print(result)
        print("="*80)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
