#!/usr/bin/env python3
"""
CodeAlive Search - Semantic code search across indexed repositories

Usage:
    python search.py "How is authentication handled?" my-repo --mode auto
    python search.py "JWT token validation" workspace:backend-team
    python search.py "React hooks patterns" react lodash --mode deep
    python search.py "user registration" my-repo --description-detail full

Examples:
    # Search current project
    python search.py "user registration logic" my-backend-repo

    # Search across workspace (multiple repos)
    python search.py "error handling patterns" workspace:platform-team

    # Deep search for complex queries
    python search.py "How do services communicate?" workspace:microservices --mode deep

    # Get full descriptions for more context
    python search.py "authentication flow" my-repo --description-detail full
"""

import sys
import json
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def _format_byte_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def format_search_results(results: dict) -> str:
    """Format search results for display."""
    if not results:
        return "No results found."

    output = []

    # Handle different response structures
    if isinstance(results, list):
        items = results
    elif "results" in results:
        items = results["results"]
    else:
        items = [results]

    if not items:
        return "No results found."

    for idx, result in enumerate(items, 1):
        # Extract location (API returns nested structure)
        location = result.get("location", {})
        file_path = location.get("path") or result.get("filePath") or result.get("file") or result.get("path")
        range_info = location.get("range", {})
        start_line = range_info.get("start", {}).get("line") or result.get("startLine") or result.get("lineNumber")
        end_line = range_info.get("end", {}).get("line") or result.get("endLine")

        # Extract data source name
        ds = result.get("dataSource", {})
        source_name = ds.get("name") if isinstance(ds, dict) else ds

        kind = result.get("kind", "")
        identifier = result.get("identifier", "")
        description = result.get("description", "")
        snippet = result.get("snippet", "")
        content_byte_size = result.get("contentByteSize")

        # Extract file path from identifier (format: "{owner/repo}::{path}::{symbol_or_chunk}")
        if not file_path and "::" in identifier:
            parts = identifier.split("::")
            if len(parts) >= 2:
                file_path = parts[1]

        # Format file:line reference
        loc_str = file_path or ""
        if loc_str and start_line and start_line > 0:
            if end_line and end_line != start_line and end_line > 0:
                loc_str = f"{file_path}:{start_line}-{end_line}"
            else:
                loc_str = f"{file_path}:{start_line}"

        # Compact output: one block per result
        output.append(f"\n--- Result #{idx} [{kind}] ---")
        if loc_str:
            output.append(f"  File: {loc_str}")
        if identifier and kind != "Chunk":
            short_id = identifier.split("::")[-1] if "::" in identifier else identifier
            if short_id != file_path:
                output.append(f"  Symbol: {short_id}")
        if source_name:
            output.append(f"  Source: {source_name}")
        if content_byte_size is not None:
            output.append(f"  Size: {_format_byte_size(content_byte_size)}")
        if description:
            output.append(f"  Description: {description}")
        elif snippet:
            output.append(f"  Content (truncated): {snippet}")

    output.append(f"\n({len(items)} results)")
    return "\n".join(output)


def main():
    """CLI interface for code search."""
    if len(sys.argv) < 3:
        print("Error: Missing required arguments.", file=sys.stderr)
        print("Usage: python search.py <query> <data_source> [data_source2...] [--mode auto|fast|deep] [--description-detail short|full]", file=sys.stderr)
        sys.exit(1)

    query = sys.argv[1]
    mode = "auto"
    description_detail = "short"
    data_sources = []

    # Parse arguments
    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--mode" and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]
            i += 2
        elif arg == "--description-detail" and i + 1 < len(sys.argv):
            description_detail = sys.argv[i + 1]
            i += 2
        elif arg == "--help":
            print(__doc__)
            sys.exit(0)
        else:
            data_sources.append(arg)
            i += 1

    if not data_sources:
        print("Error: At least one data source is required. Run datasources.py to see available sources.", file=sys.stderr)
        sys.exit(1)

    try:
        client = CodeAliveClient()

        print(f"🔍 Searching for: '{query}'", file=sys.stderr)
        print(f"📚 Data sources: {', '.join(data_sources)}", file=sys.stderr)
        print(f"⚙️  Mode: {mode}", file=sys.stderr)
        if description_detail != "short":
            print(f"📝 Description detail: {description_detail}", file=sys.stderr)
        print(file=sys.stderr)

        results = client.search(
            query=query,
            data_sources=data_sources,
            mode=mode,
            description_detail=description_detail
        )

        print(format_search_results(results))

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
