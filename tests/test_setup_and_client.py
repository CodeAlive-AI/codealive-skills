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
from api_client import CodeAliveClient, format_codealive_error  # noqa: E402


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


def test_get_datasources_with_query_sends_param_and_reports_omitted_count():
    def datasources_handler(_request):
        return 200, [
            {
                "id": "repo-1",
                "name": "backend",
                "type": "Repository",
                "relevanceReason": "Implements the checkout flow",
            }
        ], {"x-codealive-total-data-sources": "3"}  # lowercase: proxies may normalize casing

    with mock_codealive_server(
        {("GET", "/api/datasources/ready?query=add+OAuth"): datasources_handler}
    ) as (base_url, requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.get_datasources(query="add OAuth")

    assert requests[0]["path"] == "/api/datasources/ready?query=add+OAuth"
    assert result["dataSources"][0]["relevanceReason"] == "Implements the checkout flow"
    assert "1 of 3 available data sources are relevant" in result["message"]
    assert "the other 2 were omitted" in result["message"]


def test_get_datasources_query_fail_open_warns_full_list_returned():
    # No item carries relevanceReason and no total header: the backend filter did not
    # run (fail-open / disabled / older backend) and returned the full list.
    with mock_codealive_server(
        {
            ("GET", "/api/datasources/ready?query=add+OAuth"): (
                200,
                [
                    {"id": "repo-1", "name": "backend", "type": "Repository"},
                    {"id": "repo-2", "name": "frontend", "type": "Repository"},
                ],
            )
        }
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.get_datasources(query="add OAuth")

    assert len(result["dataSources"]) == 2
    assert "FULL unfiltered list" in result["message"]


def test_get_datasources_query_confident_empty_reports_nothing_relevant():
    # Empty list + total header: the filter ran and confidently matched nothing.
    # Must NOT be mistaken for fail-open (fail-open returns the full, non-empty list).
    def datasources_handler(_request):
        return 200, [], {"X-CodeAlive-Total-Data-Sources": "3"}

    with mock_codealive_server(
        {("GET", "/api/datasources/ready?query=add+OAuth"): datasources_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.get_datasources(query="add OAuth")

    assert result["dataSources"] == []
    assert "None of the 3 available data sources are relevant" in result["message"]
    assert "List without a query" in result["message"]


def test_get_datasources_query_empty_org_reports_no_sources():
    # Empty list and total header reports zero candidates: the org simply has no
    # data sources — not a relevance verdict, not a filter failure.
    def datasources_handler(_request):
        return 200, [], {"X-CodeAlive-Total-Data-Sources": "0"}

    with mock_codealive_server(
        {("GET", "/api/datasources/ready?query=add+OAuth"): datasources_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.get_datasources(query="add OAuth")

    assert result["dataSources"] == []
    assert result["message"] == "No data sources are available."


def test_get_datasources_blank_query_behaves_like_no_query():
    with mock_codealive_server(
        {
            ("GET", "/api/datasources/ready"): (
                200,
                [{"id": "repo-1", "name": "backend", "type": "Repository"}],
            )
        }
    ) as (base_url, requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.get_datasources(query="   ")

    assert result == [{"id": "repo-1", "name": "backend", "type": "Repository"}]
    assert requests[0]["path"] == "/api/datasources/ready"


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
        assert request["headers"]["Accept"] == "application/json, application/problem+json"
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


def test_api_client_fetch_artifacts_forwards_data_source():
    received_bodies: list = []

    def fetch_handler(request):
        body = json.loads(request["body"])
        received_bodies.append(body)
        return 200, {"artifacts": []}, {}

    with mock_codealive_server(
        {("POST", "/api/search/artifacts"): fetch_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        # Omitted by default…
        client.fetch_artifacts(["org/repo::src/a.py::F"])
        # …forwarded as DataSource when provided.
        client.fetch_artifacts(["org/repo::src/a.py::F"], data_source="backend")

    assert "dataSource" not in received_bodies[0]
    assert received_bodies[1]["dataSource"] == "backend"


def test_api_client_get_artifact_relationships_forwards_data_source():
    received_bodies: list = []

    def relationships_handler(request):
        body = json.loads(request["body"])
        received_bodies.append(body)
        return 200, {"sourceIdentifier": body["identifier"], "profile": body["profile"], "found": True, "relationships": []}, {}

    with mock_codealive_server(
        {("POST", "/api/search/artifact-relationships"): relationships_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        client.get_artifact_relationships("org/repo::src/a.py::F")
        client.get_artifact_relationships("org/repo::src/a.py::F", data_source="ds-main")

    assert "dataSource" not in received_bodies[0]
    assert received_bodies[1]["dataSource"] == "ds-main"


def test_api_client_ambiguous_409_surfaces_candidate_data_sources():
    # When an identifier is ambiguous and no data_source is supplied, the backend returns a 409
    # whose detail lists the candidate data sources. The client must surface those candidates so
    # the agent can retry with --data-source rather than inventing a result.
    def fetch_handler(request):
        return 409, {
            "title": "Ambiguous data source",
            "detail": "Identifier matches 2 data sources: Name='backend' Id='ds-main', Name='backend-legacy' Id='ds-master'",
        }, {}

    with mock_codealive_server(
        {("POST", "/api/search/artifacts"): fetch_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        try:
            client.fetch_artifacts(["org/repo::src/a.py::F"])
        except Exception as e:
            message = str(e)
            assert "409" in message
            assert "backend" in message and "backend-legacy" in message
        else:
            raise AssertionError("Expected an exception for the ambiguous 409 response")


# ===== Phase 1 — error contract & ObjectId preflight =====

def test_format_codealive_error_renders_rfc9457_problem_details():
    body = json.dumps({
        "type": "https://app.codealive.ai/errors/validation",
        "title": "Validation failed",
        "status": 400,
        "detail": "conversationId: must be a 24-character hex Mongo ObjectId",
        "instance": "POST /api/chat/completions",
        "errors": {
            "conversationId": ["must be a 24-character hex Mongo ObjectId"],
        },
        "requestId": "0HNLBU64JB822:00000001",
    }).encode("utf-8")

    rendered = format_codealive_error(400, body)

    assert "Validation failed" in rendered
    assert "conversationId: must be a 24-character hex Mongo ObjectId" in rendered
    assert "Details: conversationId: must be a 24-character hex Mongo ObjectId" in rendered
    assert "requestId=0HNLBU64JB822:00000001" in rendered
    assert "type=https://app.codealive.ai/errors/validation" in rendered


def test_format_codealive_error_renders_legacy_validation_errors_alias():
    # Pre-Phase-2 servers still in flight: only {message, validationErrors[]}.
    body = json.dumps({
        "message": "Validation failed",
        "validationErrors": ["Invalid conversation ID format"],
        "requestId": "0HNLBU64JB822:00000001",
    }).encode("utf-8")

    rendered = format_codealive_error(400, body)

    assert "Validation failed" in rendered
    assert "Details: Invalid conversation ID format" in rendered
    assert "requestId=0HNLBU64JB822:00000001" in rendered


def test_format_codealive_error_handles_non_json_body_and_str_input():
    assert format_codealive_error(502, b"<html>Bad Gateway</html>") == "HTTP 502: <html>Bad Gateway</html>"
    assert format_codealive_error(503, "") == "HTTP 503"
    # str input must also be tolerated (e.g. when callers re-decode bytes)
    assert format_codealive_error(503, "plain text body") == "HTTP 503: plain text body"


def test_make_request_400_uses_helper_and_surfaces_field_errors():
    def bad_handler(_request):
        return 400, {
            "type": "https://app.codealive.ai/errors/validation",
            "title": "Validation failed",
            "status": 400,
            "detail": "conversationId: must be a 24-character hex Mongo ObjectId",
            "errors": {
                "conversationId": ["must be a 24-character hex Mongo ObjectId"],
            },
            "requestId": "abc123",
        }, {}

    with mock_codealive_server(
        {("POST", "/api/chat/completions"): bad_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        try:
            client.chat("hi", data_sources=["backend"])
        except Exception as e:
            msg = str(e)
            assert "Bad request (400)" in msg
            assert "conversationId: must be a 24-character hex Mongo ObjectId" in msg
            assert "requestId=abc123" in msg
        else:
            raise AssertionError("Expected client.chat to raise on 400")


def test_chat_preflight_rejects_non_objectid_conversation_id_without_request():
    # Tracks the exact GUID from the §2 incident reproduction.
    guid = "c8d2c10f-ce4b-43f7-ae24-072c60aacc1e"
    client = CodeAliveClient(api_key="skill-test-key", base_url="https://test.local")
    try:
        client.chat("hi", conversation_id=guid)
    except ValueError as e:
        msg = str(e)
        assert "24-character hex Mongo ObjectId" in msg
        assert guid in msg
    else:
        raise AssertionError("Expected ValueError for GUID conversation_id")


def test_chat_accepts_phase3_response_shape_with_conversationid_and_messageid():
    def chat_handler(_request):
        return 200, {
            "content": "Auth is in AuthService.",
            "conversationId": "69fceb3e7b2a6a7efdd18180",
            "messageId": "69fceb3e7b2a6a7efdd18181",
        }, {}

    with mock_codealive_server(
        {("POST", "/api/chat/completions"): chat_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.chat("How does auth work?", data_sources=["backend"])

    assert result["answer"] == "Auth is in AuthService."
    assert result["conversation_id"] == "69fceb3e7b2a6a7efdd18180"
    assert result["message_id"] == "69fceb3e7b2a6a7efdd18181"


def test_chat_falls_back_to_legacy_id_envelope_when_phase3_fields_absent():
    # Pre-Phase-3 server: OpenAI-shaped envelope with id+choices only.
    def chat_handler(_request):
        return 200, {
            "id": "conv_legacy",
            "choices": [{"message": {"content": "legacy answer"}}],
        }, {}

    with mock_codealive_server(
        {("POST", "/api/chat/completions"): chat_handler}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.chat("hi", data_sources=["backend"])

    assert result["answer"] == "legacy answer"
    assert result["conversation_id"] == "conv_legacy"
    assert result["message_id"] is None  # not present in legacy envelope
