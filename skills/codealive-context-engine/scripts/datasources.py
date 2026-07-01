#!/usr/bin/env python3
"""
CodeAlive Data Sources - List available repositories and workspaces

Shows all indexed codebases available for search and consultation.
Includes current project repos, dependencies, libraries, and organizational codebases.

Usage:
    python datasources.py                  # Show ready-to-use data sources
    python datasources.py --query "TASK"   # Show only sources relevant to a task (recommended)
    python datasources.py --all            # Show all data sources (including processing)
    python datasources.py --json           # Output as JSON

Examples:
    # RECOMMENDED when you know the task: only sources relevant to it, each with a
    # relevanceReason explaining the match
    python datasources.py --query "add OAuth to the checkout flow"

    # List ready data sources
    python datasources.py

    # List all data sources (including those being processed)
    python datasources.py --all

    # Get JSON output for parsing
    python datasources.py --json

Note:
    --query runs an AI relevance filter on the backend. It fails open: if filtering is
    unavailable, the FULL list is returned and the output says so.
"""

import sys
import json
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def format_datasources(datasources: list, as_json: bool = False, message: str = "") -> str:
    """Format data sources for display.

    `message` is the relevance hint accompanying a --query'd listing: how many sources
    were omitted as non-relevant, or that filtering was unavailable and the list is full.
    """
    if as_json:
        if message:
            return json.dumps({"dataSources": datasources, "message": message}, indent=2)
        return json.dumps(datasources, indent=2)

    if not datasources:
        if message:
            return f"No data sources matched.\nℹ️  {message}"
        return "No data sources found.\nAdd repositories at https://app.codealive.ai"

    output = []
    output.append(f"\n📚 Available Data Sources ({len(datasources)} total)\n")
    output.append("="*80)
    if message:
        output.append(f"\nℹ️  {message}")

    # Group by type
    repos = [ds for ds in datasources if ds.get("type") == "Repository"]
    workspaces = [ds for ds in datasources if ds.get("type") == "Workspace"]

    if workspaces:
        output.append("\n🗂️  WORKSPACES (search across multiple repos)")
        output.append("-"*80)
        for ws in workspaces:
            name = ws.get("name", "Unknown")
            desc = ws.get("description", "No description")
            state = ws.get("state", "")

            status = f" [{state}]" if state and state != "Alive" else ""
            output.append(f"\n  📁 {name}{status}")
            output.append(f"     {desc}")
            if ws.get("relevanceReason"):
                output.append(f"     🎯 {ws['relevanceReason']}")

    if repos:
        output.append("\n\n📦 REPOSITORIES")
        output.append("-"*80)
        for repo in repos:
            name = repo.get("name", "Unknown")
            desc = repo.get("description", "No description")
            url = repo.get("url", "")
            state = repo.get("state", "")

            status = f" [{state}]" if state and state != "Alive" else ""
            output.append(f"\n  📄 {name}{status}")
            output.append(f"     {desc}")
            if repo.get("relevanceReason"):
                output.append(f"     🎯 {repo['relevanceReason']}")
            if url:
                output.append(f"     🔗 {url}")

    output.append("\n" + "="*80)
    output.append("\n💡 Usage:")
    output.append("   • Use names with search.py, grep.py, and fetch.py")
    output.append("   • Workspaces search ALL repos in the workspace")
    output.append("   • Combine multiple data sources for broader search")
    output.append("   • Pass --query 'your task' to list only the relevant sources")
    output.append("\n📖 Examples:")
    output.append("   python search.py 'auth logic' my-backend")
    output.append("   python grep.py 'AuthService' my-backend")

    return "\n".join(output)


def main():
    """CLI interface for listing data sources."""
    ready_only = True
    as_json = False
    query = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--all":
            ready_only = False
        elif arg == "--json":
            as_json = True
        elif arg == "--query":
            if i + 1 >= len(args):
                print("❌ Error: --query requires a value", file=sys.stderr)
                sys.exit(1)
            query = args[i + 1]
            i += 1
        elif arg == "--help":
            print(__doc__)
            sys.exit(0)
        i += 1

    try:
        client = CodeAliveClient()
        result = client.get_datasources(
            ready_only=ready_only,
            query=query,
            output_format="json" if as_json else "agentic",
        )
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print(result)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
