#!/usr/bin/env python3
"""
CodeAlive Fetch - Retrieve full content for code artifacts

Usage:
    python fetch.py <identifier1> [identifier2...] [--data-source NAME_OR_ID]

Examples:
    # Fetch a single artifact (symbol)
    python fetch.py "my-org/backend::src/services/auth.py::AuthService.validate_token(token: str)"

    # Fetch a file
    python fetch.py "my-org/backend::src/services/auth.py"

    # Fetch multiple artifacts
    python fetch.py "my-org/backend::src/auth.py::login" "my-org/backend::src/utils.py::helper"

    # Disambiguate an identifier that exists in more than one data source
    # (use the dataSource name or id from a search result)
    python fetch.py "my-org/backend::src/auth.py::login" --data-source "backend"

Identifiers come from semantic/grep search results (the `identifier` field).
The format is: {owner/repo}::{path}::{symbol} (for symbols/chunks)
               {owner/repo}::{path} (for files)

Pass --data-source (a data source Name or Id from a search result's `dataSource`)
to disambiguate an identifier that exists in more than one data source. Without it,
an ambiguous identifier returns a 409 listing the candidate data sources.

Maximum 50 identifiers per request.
"""

import sys
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def main():
    """CLI interface for fetching artifacts."""
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print(__doc__)
        if len(sys.argv) < 2:
            sys.exit(1)
        sys.exit(0)

    identifiers = []
    data_source = None
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--data-source":
            # Match the flag first, then require a value — otherwise a trailing "--data-source"
            # with no value would be silently appended as an identifier.
            if i + 1 >= len(sys.argv):
                print("Error: --data-source requires a value.", file=sys.stderr)
                sys.exit(1)
            data_source = sys.argv[i + 1]
            i += 2
        else:
            identifiers.append(arg)
            i += 1

    if not identifiers:
        print("Error: At least one identifier is required.", file=sys.stderr)
        sys.exit(1)

    if len(identifiers) > 50:
        print("Error: Maximum 50 identifiers per request.", file=sys.stderr)
        sys.exit(1)

    try:
        client = CodeAliveClient()

        print(f"📥 Fetching {len(identifiers)} artifact(s)", file=sys.stderr)
        if data_source:
            print(f"   data source: {data_source}", file=sys.stderr)
        print(file=sys.stderr)

        result = client.fetch_artifacts(identifiers=identifiers, data_source=data_source)
        print(result)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
