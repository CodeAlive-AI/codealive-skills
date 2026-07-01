#!/usr/bin/env python3
"""Get a bounded repository file tree."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def main():
    data_source = None
    path = None
    max_depth = None
    max_nodes = None
    output_depth = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--help":
            print("Usage: python tree.py [--data-source NAME_OR_ID] [--path PATH] [--max-depth N] [--max-nodes N] [--output-depth N]")
            return
        if arg in {"--data-source", "--path", "--max-depth", "--max-nodes", "--output-depth"}:
            if i + 1 >= len(args):
                print(f"Error: {arg} requires a value.", file=sys.stderr)
                sys.exit(1)
            value = args[i + 1]
            if arg == "--data-source":
                data_source = value
            elif arg == "--path":
                path = value
            elif arg == "--max-depth":
                max_depth = int(value)
            elif arg == "--max-nodes":
                max_nodes = int(value)
            else:
                output_depth = int(value)
            i += 2
        else:
            print(f"Error: unknown argument '{arg}'", file=sys.stderr)
            sys.exit(1)

    try:
        print(CodeAliveClient().get_file_tree(
            data_source=data_source,
            path=path,
            max_depth=max_depth,
            max_nodes=max_nodes,
            output_depth=output_depth,
        ))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
