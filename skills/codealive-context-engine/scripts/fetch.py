#!/usr/bin/env python3
"""
CodeAlive Fetch - Retrieve full content for code artifacts

Usage:
    python fetch.py <identifier1> [identifier2...]

Examples:
    # Fetch a single artifact (symbol)
    python fetch.py "my-org/backend::src/services/auth.py::AuthService.validate_token(token: str)"

    # Fetch a file
    python fetch.py "my-org/backend::src/services/auth.py"

    # Fetch multiple artifacts
    python fetch.py "my-org/backend::src/auth.py::login" "my-org/backend::src/utils.py::helper"

Identifiers come from codebase_search results (the `identifier` field).
The format is: {owner/repo}::{path}::{symbol} (for symbols/chunks)
               {owner/repo}::{path} (for files)

Maximum 20 identifiers per request.
"""

import sys
import json
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def format_artifacts(data: dict) -> str:
    """Format fetched artifacts for display."""
    artifacts = data.get("artifacts", [])
    if not artifacts:
        return "No artifacts returned."

    output = []
    count = 0

    for artifact in artifacts:
        content = artifact.get("content")
        if content is None:
            continue

        count += 1
        identifier = artifact.get("identifier", "unknown")
        content_byte_size = artifact.get("contentByteSize")

        size_str = f" ({content_byte_size} bytes)" if content_byte_size else ""
        output.append(f"\n{'='*60}")
        output.append(f"📄 {identifier}{size_str}")
        output.append(f"{'='*60}")
        output.append(content)

    if not output:
        return "No artifacts found."

    output.append(f"\n({count} artifact(s))")
    return "\n".join(output)


def main():
    """CLI interface for fetching artifacts."""
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print(__doc__)
        if len(sys.argv) < 2:
            sys.exit(1)
        sys.exit(0)

    identifiers = sys.argv[1:]

    if len(identifiers) > 20:
        print("Error: Maximum 20 identifiers per request.", file=sys.stderr)
        sys.exit(1)

    try:
        client = CodeAliveClient()

        print(f"📥 Fetching {len(identifiers)} artifact(s)", file=sys.stderr)
        print(file=sys.stderr)

        result = client.fetch_artifacts(identifiers=identifiers)

        print(format_artifacts(result))

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
