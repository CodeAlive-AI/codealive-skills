#!/usr/bin/env python3
"""Read one repository-relative file path."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print("Usage: python read_file.py <path> [--data-source NAME_OR_ID] [--start-line N] [--end-line N]")
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    file_path = sys.argv[1]
    data_source = None
    start_line = None
    end_line = None

    i = 2
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in {"--data-source", "--start-line", "--end-line"}:
            if i + 1 >= len(sys.argv):
                print(f"Error: {arg} requires a value.", file=sys.stderr)
                sys.exit(1)
            value = sys.argv[i + 1]
            if arg == "--data-source":
                data_source = value
            elif arg == "--start-line":
                start_line = int(value)
            else:
                end_line = int(value)
            i += 2
        else:
            print(f"Error: unknown argument '{arg}'", file=sys.stderr)
            sys.exit(1)

    try:
        print(CodeAliveClient().read_file(
            path=file_path,
            data_source=data_source,
            start_line=start_line,
            end_line=end_line,
        ))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
