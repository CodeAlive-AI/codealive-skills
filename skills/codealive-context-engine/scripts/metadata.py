#!/usr/bin/env python3
"""Run a read-only ArtifactQuery metadata statement."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print("Usage: python metadata.py <statement> [data_source ...] [--json]")
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    statement = sys.argv[1]
    data_sources = []
    as_json = False
    for arg in sys.argv[2:]:
        if arg == "--json":
            as_json = True
        else:
            data_sources.append(arg)

    try:
        result = CodeAliveClient().query_artifact_metadata(
            statement=statement,
            data_sources=data_sources or None,
            output_format="json" if as_json else "agentic",
        )
        print(json.dumps(result, indent=2) if as_json else result)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
