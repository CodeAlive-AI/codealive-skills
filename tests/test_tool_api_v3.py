"""Tool API v3 tests for the CodeAlive skills package."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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


skill_setup_module = _load_module(SKILL_ROOT / "setup.py", "codealive_skill_setup_v3")
skill_version_module = _load_module(SKILL_ROOT / "scripts" / "get_version.py", "codealive_skill_version_v3")
sys.path.insert(0, str(LIB_ROOT))
from api_client import CodeAliveClient, format_codealive_error  # noqa: E402


def _tool_response(name: str = "ok"):
    return {"rendered": f"<{name}>rendered</{name}>", "obj": {"name": name}}


def _header(headers: dict[str, str], name: str) -> str | None:
    return next((value for key, value in headers.items() if key.lower() == name.lower()), None)


def test_get_version_matches_plugin_release_version():
    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))

    assert skill_version_module.get_version() == "3.0.0"
    assert skill_version_module.get_version() == plugin["version"]


def test_get_version_script_returns_json_without_authentication():
    result = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "get_version.py")],
        check=True,
        capture_output=True,
        text=True,
        env={},
    )

    assert json.loads(result.stdout) == {
        "name": "codealive-context-engine",
        "version": "3.0.0",
    }


def test_setup_normalize_base_url_accepts_origin_and_api_suffix():
    assert skill_setup_module.normalize_base_url("https://codealive.example.com") == "https://codealive.example.com"
    assert skill_setup_module.normalize_base_url("https://codealive.example.com/api") == "https://codealive.example.com"
    assert skill_setup_module.normalize_base_url("https://codealive.example.com/internal/api/") == "https://codealive.example.com/internal"


def test_verify_key_uses_tool_api_v3_and_normalizes_base_url():
    with mock_codealive_server(
        {
            ("POST", "/api/tools/get_data_sources"): (
                200,
                {"obj": {"data_sources": [{"id": "repo-1", "name": "backend", "type": "Repository"}]}},
            )
        }
    ) as (base_url, requests):
        ok, message = skill_setup_module.verify_key("skill-test-key", f"{base_url}/api")

    assert ok is True
    assert "1 data source available" in message
    assert requests[0]["method"] == "POST"
    assert requests[0]["path"] == "/api/tools/get_data_sources"
    assert requests[0]["headers"]["Authorization"] == "Bearer skill-test-key"
    assert _header(requests[0]["headers"], "X-CodeAlive-Integration") == "skills"
    assert _header(requests[0]["headers"], "X-CodeAlive-Tool") == "get_data_sources"
    assert json.loads(requests[0]["body"]) == {"ready_only": True, "output_format": "json"}


def test_client_posts_canonical_payload_and_returns_rendered_by_default():
    def semantic_handler(request):
        payload = json.loads(request["body"])
        assert payload == {
            "question": "How does auth work?",
            "data_sources": ["backend"],
            "paths": ["src"],
            "extensions": [".py"],
            "max_results": 7,
            "exclude_markdown": True,
            "output_format": "agentic",
        }
        assert _header(request["headers"], "X-CodeAlive-Integration") == "skills"
        assert _header(request["headers"], "X-CodeAlive-Tool") == "semantic_search"
        assert _header(request["headers"], "X-CodeAlive-Client") == "skills-v3"
        return 200, _tool_response("semantic"), {}

    with mock_codealive_server({("POST", "/api/tools/semantic_search"): semantic_handler}) as (base_url, requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.semantic_search(
            "How does auth work?",
            ["backend"],
            paths=["src"],
            extensions=[".py"],
            max_results=7,
            exclude_markdown=True,
        )

    assert result == "<semantic>rendered</semantic>"
    assert len(requests) == 1


def test_client_json_mode_returns_obj():
    with mock_codealive_server(
        {("POST", "/api/tools/get_artifact_query_schema"): (200, _tool_response("schema"))}
    ) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        result = client.get_artifact_query_schema(output_format="json")

    assert result == {"name": "schema"}


def test_client_preserves_both_repairable_error_projections():
    error_obj = {
        "error": {
            "code": "invalid_tool_arguments",
            "message": "question is required",
            "retry": "yes - repair the tool arguments and call the tool again",
            "try": "Provide question and retry.",
        }
    }
    envelope = {
        "obj": error_obj,
        "rendered": "<tool_error><code>invalid_tool_arguments</code></tool_error>",
    }
    routes = {("POST", "/api/tools/semantic_search"): (200, envelope)}

    with mock_codealive_server(routes) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        agentic = client.semantic_search("valid locally", ["backend"], output_format="agentic")
        structured = client.semantic_search("valid locally", ["backend"], output_format="json")

    assert agentic == envelope["rendered"]
    assert structured == error_obj


def test_client_methods_cover_all_v3_tools():
    seen = []

    def handler(request):
        seen.append((request["path"], json.loads(request["body"]), _header(request["headers"], "X-CodeAlive-Tool")))
        tool_name = request["path"].rsplit("/", 1)[1]
        return 200, _tool_response(tool_name), {}

    routes = {
        ("POST", f"/api/tools/{tool}"): handler
        for tool in [
            "get_data_sources",
            "semantic_search",
            "grep_search",
            "get_repository_ontology",
            "get_file_tree",
            "read_file",
            "fetch_artifacts",
            "get_artifact_relationships",
            "get_artifact_query_schema",
            "query_artifact_metadata",
            "chat",
        ]
    }
    with mock_codealive_server(routes) as (base_url, _requests):
        client = CodeAliveClient(api_key="skill-test-key", base_url=base_url)
        assert client.get_datasources(query="auth")
        assert client.semantic_search("How auth works?", ["backend"])
        assert client.grep_search("AuthService", ["backend"], regex=True)
        assert client.get_repository_ontology("backend")
        assert client.get_file_tree("backend", path="src", max_depth=2)
        assert client.read_file("README.md", data_source="backend", start_line=1, end_line=5)
        assert client.fetch_artifacts(["repo::README.md"], data_source="backend")
        assert client.get_artifact_relationships("repo::Foo", profile="allRelevant", data_source="backend")
        assert client.get_artifact_query_schema(entity="files")
        assert client.query_artifact_metadata("SELECT path FROM files LIMIT 5", ["backend"])
        assert client.chat("Summarize auth. Prior context: none.", ["backend"])

    assert [item[2] for item in seen] == [
        "get_data_sources",
        "semantic_search",
        "grep_search",
        "get_repository_ontology",
        "get_file_tree",
        "read_file",
        "fetch_artifacts",
        "get_artifact_relationships",
        "get_artifact_query_schema",
        "query_artifact_metadata",
        "chat",
    ]
    assert all(item[1]["output_format"] == "agentic" for item in seen)
    assert seen[7][1]["max_count_per_type"] == 50
    assert "conversation_id" not in seen[-1][1]


def test_cli_scripts_call_tool_api_v3():
    def handler(request):
        tool_name = request["path"].rsplit("/", 1)[1]
        return 200, _tool_response(tool_name), {}

    tools = [
        ("datasources.py", [], "get_data_sources"),
        ("search.py", ["How auth works?", "backend"], "semantic_search"),
        ("grep.py", ["AuthService", "backend"], "grep_search"),
        ("ontology.py", ["backend"], "get_repository_ontology"),
        ("tree.py", ["--data-source", "backend", "--max-depth", "2"], "get_file_tree"),
        ("read_file.py", ["README.md", "--data-source", "backend"], "read_file"),
        ("fetch.py", ["repo::README.md", "--data-source", "backend"], "fetch_artifacts"),
        ("relationships.py", ["repo::Foo", "--profile", "callsOnly"], "get_artifact_relationships"),
        ("schema.py", [], "get_artifact_query_schema"),
        ("metadata.py", ["SELECT path FROM files LIMIT 5", "backend"], "query_artifact_metadata"),
        ("chat.py", ["Summarize auth", "backend"], "chat"),
    ]
    routes = {("POST", f"/api/tools/{tool_name}"): handler for _, _, tool_name in tools}

    with mock_codealive_server(routes) as (base_url, requests):
        env = {
            **os.environ,
            "CODEALIVE_API_KEY": "skill-test-key",
            "CODEALIVE_BASE_URL": base_url,
        }
        for script, args, tool_name in tools:
            result = subprocess.run(
                [sys.executable, str(SKILL_ROOT / "scripts" / script), *args],
                env=env,
                text=True,
                capture_output=True,
                timeout=15,
            )
            assert result.returncode == 0, result.stderr
            assert f"<{tool_name}>rendered</{tool_name}>" in result.stdout

    assert [_header(request["headers"], "X-CodeAlive-Tool") for request in requests] == [tool for _, _, tool in tools]
    assert all(json.loads(request["body"])["output_format"] == "agentic" for request in requests)


def test_format_codealive_error_reads_problem_details():
    body = json.dumps(
        {
            "title": "Bad request",
            "detail": "Missing question",
            "errors": {"question": ["required"]},
            "requestId": "req-1",
        }
    )

    message = format_codealive_error(400, body)

    assert "Bad request" in message
    assert "Missing question" in message
    assert "question: required" in message
    assert "requestId=req-1" in message
