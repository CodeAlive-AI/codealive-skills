"""Tests for setup.py and the shared API client."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from helpers import mock_codealive_server


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "codealive-context-engine"
LIB_ROOT = SKILL_ROOT / "scripts" / "lib"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


skill_setup_module = _load_module(SKILL_ROOT / "setup.py", "codealive_skill_setup")
sys.path.insert(0, str(LIB_ROOT))
from api_client import CodeAliveClient  # noqa: E402


def test_setup_normalize_base_url_accepts_origin_and_api_suffix():
    assert skill_setup_module.normalize_base_url("https://codealive.example.com") == "https://codealive.example.com"
    assert skill_setup_module.normalize_base_url("https://codealive.example.com/api") == "https://codealive.example.com"
    assert skill_setup_module.normalize_base_url("https://codealive.example.com/internal/api/") == "https://codealive.example.com/internal"


def test_verify_key_uses_ready_endpoint_and_normalizes_base_url():
    with mock_codealive_server(
        {
            ("GET", "/api/datasources/ready"): (
                200,
                [{"id": "repo-1", "name": "backend", "type": "Repository"}],
            )
        }
    ) as (base_url, requests):
        ok, message = skill_setup_module.verify_key("skill-test-key", f"{base_url}/api")

    assert ok is True
    assert "1 data source available" in message
    assert len(requests) == 1
    assert requests[0]["method"] == "GET"
    assert requests[0]["path"] == "/api/datasources/ready"
    assert requests[0]["headers"]["Authorization"] == "Bearer skill-test-key"
    assert requests[0]["headers"]["Content-Type"] == "application/json"
    assert requests[0]["body"] == ""


def test_api_client_normalizes_base_url_and_calls_ready_endpoint():
    with mock_codealive_server(
        {
            ("GET", "/api/datasources/ready"): (
                200,
                [{"id": "repo-1", "name": "backend", "type": "Repository"}],
            )
        }
    ) as (base_url, requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=f"{base_url}/api")
        result = client.get_datasources()

    assert result == [{"id": "repo-1", "name": "backend", "type": "Repository"}]
    assert requests[0]["path"] == "/api/datasources/ready"
    assert requests[0]["headers"]["Authorization"] == "Bearer skill-test-key"


def test_api_client_search_fetch_and_chat_use_expected_endpoints():
    def search_handler(request):
        assert "Query=auth" in request["path"]
        assert "Names=backend" in request["path"]
        return 200, {
            "results": [
                {
                    "identifier": "org/repo::src/auth.py::AuthService",
                    "kind": "Class",
                    "description": "Handles auth",
                    "location": {"path": "src/auth.py", "range": {"start": {"line": 10}, "end": {"line": 20}}},
                }
            ]
        }, {}

    def fetch_handler(request):
        payload = json.loads(request["body"])
        assert payload["identifiers"] == ["org/repo::src/auth.py::AuthService"]
        return 200, {"artifacts": [{"identifier": payload["identifiers"][0], "content": "class AuthService:\n    pass\n"}]}, {}

    def chat_handler(request):
        payload = json.loads(request["body"])
        assert payload["messages"][0]["content"] == "How does auth work?"
        assert payload["names"] == ["backend"]
        return 200, {"id": "conv_123", "choices": [{"message": {"content": "Auth is handled in AuthService."}}]}, {}

    with mock_codealive_server(
        {
            ("GET", "/api/search?Query=auth&Mode=auto&IncludeContent=false&DescriptionDetail=Short&Names=backend"): search_handler,
            ("POST", "/api/search/artifacts"): fetch_handler,
            ("POST", "/api/chat/completions"): chat_handler,
        }
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        search_result = client.search("auth", ["backend"])
        fetch_result = client.fetch_artifacts(["org/repo::src/auth.py::AuthService"])
        chat_result = client.chat("How does auth work?", data_sources=["backend"])

    assert search_result["results"][0]["identifier"] == "org/repo::src/auth.py::AuthService"
    assert fetch_result["artifacts"][0]["identifier"] == "org/repo::src/auth.py::AuthService"
    assert chat_result["answer"] == "Auth is handled in AuthService."
    assert chat_result["conversation_id"] == "conv_123"


def test_api_client_canonical_search_endpoints_use_scope_params():
    def semantic_handler(request):
        assert "Query=auth" in request["path"]
        assert "Names=backend" in request["path"]
        assert "Paths=src%2Fauth.py" in request["path"]
        assert "Extensions=.py" in request["path"]
        assert "MaxResults=7" in request["path"]
        return 200, {
            "results": [
                {
                    "identifier": "org/repo::src/auth.py::AuthService",
                    "location": {"path": "src/auth.py"},
                }
            ]
        }, {}

    def grep_handler(request):
        assert "Query=AuthService" in request["path"]
        assert "Regex=true" in request["path"]
        return 200, {
            "results": [
                {
                    "identifier": "org/repo::src/auth.py",
                    "matchCount": 1,
                    "matches": [{"lineNumber": 12, "lineText": "class AuthService:"}],
                }
            ]
        }, {}

    with mock_codealive_server(
        {
            ("GET", "/api/search/semantic?Query=auth&Names=backend&Paths=src%2Fauth.py&Extensions=.py&MaxResults=7"): semantic_handler,
            ("GET", "/api/search/grep?Query=AuthService&Names=backend&Regex=true"): grep_handler,
        }
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        semantic_result = client.semantic_search(
            "auth",
            ["backend"],
            paths=["src/auth.py"],
            extensions=[".py"],
            max_results=7,
        )
        grep_result = client.grep_search("AuthService", ["backend"], regex=True)

    assert semantic_result["results"][0]["identifier"] == "org/repo::src/auth.py::AuthService"
    assert grep_result["results"][0]["matchCount"] == 1


def test_api_client_get_artifact_relationships_posts_expected_body():
    received_bodies: list = []

    def relationships_handler(request):
        body = json.loads(request["body"])
        received_bodies.append(body)
        return 200, {
            "sourceIdentifier": body["identifier"],
            "profile": body["profile"],
            "found": True,
            "relationships": [
                {
                    "relationType": "OutgoingCalls",
                    "totalCount": 2,
                    "returnedCount": 2,
                    "truncated": False,
                    "items": [
                        {
                            "identifier": "org/repo::src/db.py::query",
                            "filePath": "src/db.py",
                            "startLine": 42,
                            "shortSummary": "Runs SQL",
                        },
                        {
                            "identifier": "org/repo::src/cache.py::get",
                            "filePath": "src/cache.py",
                            "startLine": 10,
                        },
                    ],
                }
            ],
        }, {}

    with mock_codealive_server(
        {("POST", "/api/search/artifact-relationships"): relationships_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.get_artifact_relationships(
            "org/repo::src/svc.py::Service",
            profile="allRelevant",
            max_count_per_type=25,
        )

    # Body translates MCP-friendly profile to backend enum + carries max-count cap
    assert received_bodies == [
        {
            "identifier": "org/repo::src/svc.py::Service",
            "profile": "AllRelevant",
            "maxCountPerType": 25,
        }
    ]
    assert result["found"] is True
    assert result["relationships"][0]["relationType"] == "OutgoingCalls"
    assert len(result["relationships"][0]["items"]) == 2


def test_api_client_get_artifact_relationships_rejects_unknown_profile():
    client = CodeAliveClient(api_key="skill-test-key", base_url="https://test.local")
    try:
        client.get_artifact_relationships("id", profile="bogus")
    except ValueError as e:
        assert "Unsupported profile" in str(e)
    else:
        raise AssertionError("ValueError was not raised for unknown profile")
