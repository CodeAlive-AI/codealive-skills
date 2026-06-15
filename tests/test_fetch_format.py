"""Unit tests for fetch.py artifact formatting — not-found surfacing.

A requested identifier the backend cannot resolve (or that is outside the caller's scope)
must never be dropped silently: it has to appear in an explicit "not found" section with the
concrete identifier and a re-check/retry hint.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FETCH_PATH = REPO_ROOT / "skills" / "codealive-context-engine" / "scripts" / "fetch.py"


def _load_fetch():
    spec = importlib.util.spec_from_file_location("codealive_fetch", FETCH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


fetch = _load_fetch()
format_artifacts = fetch.format_artifacts


def test_found_artifact_is_rendered():
    data = {"artifacts": [
        {"identifier": "org/repo::a.py::F", "found": True, "content": "def f():\n    pass", "contentByteSize": 17},
    ]}
    out = format_artifacts(data, requested=["org/repo::a.py::F"])
    assert "org/repo::a.py::F" in out
    assert "not found or inaccessible" not in out


def test_explicit_not_found_is_surfaced_with_concrete_id_and_hint():
    data = {"artifacts": [
        {"identifier": "org/repo::a.py::F", "found": True, "content": "x"},
        {"identifier": "org/repo::missing.py::G", "found": False, "content": None},
    ]}
    out = format_artifacts(data, requested=["org/repo::a.py::F", "org/repo::missing.py::G"])
    assert "1 requested identifier(s) not found" in out
    assert "org/repo::missing.py::G" in out
    assert "Do NOT silently omit" in out
    # the found one is still rendered
    assert "📄 org/repo::a.py::F" in out


def test_legacy_backend_without_found_flag_falls_back_to_null_content():
    data = {"artifacts": [
        {"identifier": "org/repo::missing.py::G", "content": None},
    ]}
    out = format_artifacts(data, requested=["org/repo::missing.py::G"])
    assert "not found or inaccessible" in out
    assert "org/repo::missing.py::G" in out


def test_found_but_empty_content_is_rendered_not_missing():
    data = {"artifacts": [
        {"identifier": "org/repo::a.py::F", "found": True, "content": ""},
    ]}
    out = format_artifacts(data, requested=["org/repo::a.py::F"])
    assert "📄 org/repo::a.py::F" in out
    assert "not found or inaccessible" not in out


def test_all_found_has_no_not_found_section():
    data = {"artifacts": [
        {"identifier": "org/repo::a.py::F", "found": True, "content": "x"},
    ]}
    out = format_artifacts(data, requested=["org/repo::a.py::F"])
    assert "not found or inaccessible" not in out


def test_backstop_surfaces_id_backend_never_echoed():
    data = {"artifacts": [
        {"identifier": "org/repo::a.py::F", "found": True, "content": "x"},
    ]}
    out = format_artifacts(data, requested=["org/repo::a.py::F", "org/repo::ghost.py::Z"])
    assert "org/repo::ghost.py::Z" in out
    assert "1 requested identifier(s) not found" in out
