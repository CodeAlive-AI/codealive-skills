#!/usr/bin/env python3
"""Get repository ontology and high-level orientation for one repository."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def main():
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] == "--help"):
        print("Usage: python ontology.py [data_source]", file=sys.stderr)
        sys.exit(0 if len(sys.argv) == 2 else 1)

    data_source = sys.argv[1] if len(sys.argv) == 2 else None
    try:
        print(CodeAliveClient().get_repository_ontology(data_source=data_source))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
