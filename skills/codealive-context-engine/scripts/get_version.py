#!/usr/bin/env python3
"""Return the installed CodeAlive Context Engine skill version."""

import json
from pathlib import Path


VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def get_version() -> str:
    """Return the current installed skill version."""
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def main() -> None:
    print(json.dumps({"name": "codealive-context-engine", "version": get_version()}))


if __name__ == "__main__":
    main()
