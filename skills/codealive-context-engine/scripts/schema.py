#!/usr/bin/env python3
"""Get the ArtifactQuery schema."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def main():
    entity = None
    include_examples = True
    as_json = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--help":
            print("Usage: python schema.py [--entity ENTITY] [--no-examples] [--json]")
            return
        if arg == "--entity":
            if i + 1 >= len(args):
                print("Error: --entity requires a value.", file=sys.stderr)
                sys.exit(1)
            entity = args[i + 1]
            i += 2
        elif arg == "--no-examples":
            include_examples = False
            i += 1
        elif arg == "--json":
            as_json = True
            i += 1
        else:
            print(f"Error: unknown argument '{arg}'", file=sys.stderr)
            sys.exit(1)

    try:
        result = CodeAliveClient().get_artifact_query_schema(
            entity=entity,
            include_examples=include_examples,
            output_format="json" if as_json else "agentic",
        )
        print(json.dumps(result, indent=2) if as_json else result)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
