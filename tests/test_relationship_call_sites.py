"""Call-site rendering in the relationships script.

The failure mode is silent in both directions: a renderer that drops positions produces output that
looks perfectly normal, and one that prints a heading for an unknown position tells the agent the
call happens nowhere. Both are asserted here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPO_ROOT / "skills" / "codealive-context-engine" / "scripts"


def _load_relationships():
    spec = importlib.util.spec_from_file_location(
        "codealive_relationships_call_sites", SCRIPTS_ROOT / "relationships.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


relationships = _load_relationships()


def _item(**overrides):
    item = {
        "identifier": "my-org/backend::src/db.py::query",
        "filePath": "src/db.py",
        "startLine": 42,
    }
    item.update(overrides)
    return item


def test_known_positions_are_rendered_as_call_sites() -> None:
    # Arrange
    item = _item(
        callSites=[{"filePath": "src/svc.py", "line": 17}],
        callSiteCount=1,
    )

    # Act
    lines = relationships._format_call_sites(item)

    # Assert
    assert lines == ["      ↪ called at src/svc.py:17"]


def test_confidence_is_shown_only_when_the_position_is_approximate() -> None:
    # Arrange
    item = _item(
        callSites=[
            {"filePath": "src/svc.py", "line": 17},
            {"filePath": "src/svc.py", "line": 88, "confidence": 0.6},
        ],
        callSiteCount=2,
    )

    # Act
    lines = relationships._format_call_sites(item)

    # Assert
    assert lines[0] == "      ↪ called at src/svc.py:17"
    assert lines[1] == "      ↪ called at src/svc.py:88  (~60% confident)"


def test_a_capped_list_says_how_many_were_withheld() -> None:
    # Arrange
    item = _item(
        callSites=[{"filePath": "src/svc.py", "line": 17}],
        callSiteCount=4,
    )

    # Act
    lines = relationships._format_call_sites(item)

    # Assert
    assert lines[-1] == "      ↪ … 3 more call site(s) not shown"


def test_an_unindexed_position_renders_nothing_at_all() -> None:
    # An empty heading here would read as "this call happens nowhere", which is the opposite of
    # what a missing position means.
    # Arrange
    without_key = _item()
    explicit_empty = _item(callSites=[], callSiteCount=0)

    # Act
    from_missing = relationships._format_call_sites(without_key)
    from_empty = relationships._format_call_sites(explicit_empty)

    # Assert
    assert from_missing == []
    assert from_empty == []
