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

Maximum 20 identifiers per request.
"""

import sys
import json
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from api_client import CodeAliveClient


def _add_line_numbers(content: str, start_line: int = 1) -> str:
    """Add line numbers to content for easier navigation."""
    if not content:
        return content
    lines = content.split("\n")
    width = len(str(start_line + len(lines) - 1))
    numbered = [f"{start_line + i:>{width}} | {line}" for i, line in enumerate(lines)]
    return "\n".join(numbered)


def _has_any_calls(relationships: dict) -> bool:
    """True if a relationships preview has at least one outgoing/incoming call."""
    for key in ("outgoingCallsCount", "incomingCallsCount"):
        count = relationships.get(key)
        if count and count > 0:
            return True
    return False


def _format_relationships_preview(relationships: dict) -> list:
    """Format the inline preview of call relationships returned with each artifact.

    Returns a list of output lines (possibly empty).
    """
    lines: list = []

    for direction, key, label in (
        ("outgoing", "outgoingCalls", "↗ outgoing_calls"),
        ("incoming", "incomingCalls", "↙ incoming_calls"),
    ):
        count = relationships.get(f"{key}Count")
        if count is None:
            continue
        calls = relationships.get(key) or []

        lines.append(f"  {label} ({count}):")
        if not calls:
            lines.append("    (none in preview)")
            continue
        for call in calls:
            ident = call.get("identifier", "")
            summary = call.get("summary")
            if summary:
                lines.append(f"    • {ident}")
                lines.append(f"        📝 {summary}")
            else:
                lines.append(f"    • {ident}")

    return lines


def _data_source_miss_hint(data_source: str) -> str:
    """Recovery hint when a data-source-scoped fetch returns nothing."""
    return (
        f'\n💡 Hint: nothing was found in data source "{data_source}". The identifier may belong to a '
        "different data source, or the --data-source value may be wrong. Try: re-run with --data-source "
        "set to a different candidate (use the Source name or id from your search results, or run "
        "datasources.py), or drop --data-source entirely — an ambiguous identifier then returns a 409 "
        "listing the candidate data sources to choose from."
    )


def _not_found_lines(not_found: list) -> list:
    """Lines listing requested identifiers the backend could not resolve or that are
    outside the caller's access scope, with a re-check/retry hint."""
    lines = [
        f"\n{'='*60}",
        f"⚠️  {len(not_found)} requested identifier(s) not found or inaccessible:",
    ]
    for identifier in not_found:
        lines.append(f"   • {identifier}")
    lines.append(f"{'='*60}")
    lines.append(
        "💡 Do NOT silently omit these. A not-found entry means the identifier did not "
        "resolve, or points outside the data sources this key can read — it is NOT proof "
        "the code is absent. Re-check those exact identifiers, re-run search.py or grep.py "
        "to get fresh ids, then re-fetch the problematic ones; if they still cannot be "
        "retrieved, tell the user which artifacts could not be fetched."
    )
    return lines


def format_artifacts(data: dict, data_source: str = None, requested: list = None) -> str:
    """Format fetched artifacts for display.

    Requested identifiers the backend could not resolve — or that are outside the caller's
    access scope — come back with ``found: false`` (older backends omit the flag and return
    ``content: null``). They are NOT dropped silently: each concrete identifier is listed in
    a "not found" section with a hint to re-check the ids and retry the problematic ones.
    A ``found: true`` artifact with empty content is still shown (it was located).
    ``requested`` is the original identifier list; it backstops the diff so an id the
    backend never echoed back is still surfaced as not-found.
    """
    artifacts = data.get("artifacts", [])

    output = []
    count = 0
    has_any_relationships = False
    returned_identifiers = set()
    not_found = []

    for artifact in artifacts:
        identifier = artifact.get("identifier", "unknown")
        returned_identifiers.add(identifier)

        content = artifact.get("content")
        # Prefer the backend's explicit `found` flag; fall back to content-is-null for
        # older backends that don't emit it yet.
        found = artifact.get("found")
        is_missing = (found is False) if found is not None else (content is None)
        if is_missing:
            not_found.append(identifier)
            continue

        count += 1
        content_byte_size = artifact.get("contentByteSize")

        size_str = f" ({content_byte_size} bytes)" if content_byte_size else ""
        output.append(f"\n{'='*60}")
        output.append(f"📄 {identifier}{size_str}")
        output.append(f"{'='*60}")
        start_line = artifact.get("startLine") or 1
        output.append(_add_line_numbers(content or "", start_line))

        relationships = artifact.get("relationships")
        if relationships is not None:
            preview_lines = _format_relationships_preview(relationships)
            if preview_lines:
                output.append("\n--- relationships (preview) ---")
                output.extend(preview_lines)
                if _has_any_calls(relationships):
                    has_any_relationships = True

    # Backstop: any requested identifier the backend never echoed back is also missing.
    if requested:
        for identifier in requested:
            if identifier not in returned_identifiers and identifier not in not_found:
                not_found.append(identifier)

    if count > 0:
        output.append(f"\n({count} artifact(s))")

    if has_any_relationships:
        output.append(
            "\n💡 Hint: the relationships shown above are a preview (up to 3 calls "
            "per direction).\n"
            "   To see the full call graph, inheritance, or references for an "
            "artifact, run:\n"
            "     python relationships.py <identifier> "
            "[--profile callsOnly|inheritanceOnly|allRelevant|referencesOnly]"
        )

    if not_found:
        output.extend(_not_found_lines(not_found))

    if count == 0:
        # Nothing was actually fetched. Keep the data-source-specific recovery hint when a
        # selector was supplied; the not-found section above already lists the ids.
        if data_source:
            output.append(_data_source_miss_hint(data_source))
        if not output:
            return "No artifacts returned."

    return "\n".join(output)


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
