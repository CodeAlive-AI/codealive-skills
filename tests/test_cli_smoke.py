"""CLI smoke tests for the CodeAlive skill scripts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from helpers import mock_codealive_server


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "codealive-context-engine"


def _run(script_name: str, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = SKILL_ROOT / "scripts" / script_name
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_datasources_search_fetch_and_chat_scripts_work_against_mock_backend():
    def search_handler(_request):
        return 200, {
            "results": [
                {
                    "identifier": "org/repo::src/auth.py::AuthService",
                    "kind": "Class",
                    "description": "Handles auth",
                    "location": {"path": "src/auth.py", "range": {"start": {"line": 10}, "end": {"line": 20}}},
                    "contentByteSize": 2048,
                }
            ]
        }, {}

    def fetch_handler(_request):
        return 200, {
            "artifacts": [
                {
                    "identifier": "org/repo::src/auth.py::AuthService.login",
                    "content": "def login(user, pwd):\n    return True\n",
                    "startLine": 10,
                    "contentByteSize": 38,
                    "relationships": {
                        "outgoingCallsCount": 5,
                        "outgoingCalls": [
                            {"identifier": "org/repo::src/db.py::query", "summary": "Runs SQL"},
                        ],
                        "incomingCallsCount": 0,
                        "incomingCalls": None,
                    },
                }
            ]
        }, {}

    def chat_handler(_request):
        return 200, {
            "id": "conv_123",
            "choices": [{"message": {"content": "Auth is handled in AuthService."}}],
        }, {}

    with mock_codealive_server(
        {
            ("GET", "/api/datasources/ready"): (
                200,
                [{"id": "repo-1", "name": "backend", "type": "Repository", "description": "Main backend"}],
            ),
            ("GET", "/api/search?Query=auth&Mode=auto&IncludeContent=false&DescriptionDetail=Short&Names=backend"): search_handler,
            ("POST", "/api/search/artifacts"): fetch_handler,
            ("POST", "/api/chat/completions"): chat_handler,
        }
    ) as (base_url, requests):
        env = {
            **os.environ,
            "CODEALIVE_API_KEY": "skill-test-key",
            "CODEALIVE_BASE_URL": f"{base_url}/api",
        }

        datasources = _run("datasources.py", "--json", env=env)
        search = _run("search.py", "auth", "backend", env=env)
        fetch = _run("fetch.py", "org/repo::src/auth.py::AuthService.login", env=env)
        chat = _run("chat.py", "How does auth work?", "backend", env=env)

    assert datasources.returncode == 0, datasources.stderr
    assert json.loads(datasources.stdout)[0]["name"] == "backend"

    assert search.returncode == 0, search.stderr
    assert "src/auth.py:10-20" in search.stdout
    assert "Handles auth" in search.stdout
    # search must surface the "description is only a triage pointer" hint
    assert "triage" in search.stdout
    assert "fetch.py" in search.stdout
    assert "ground truth" in search.stdout

    assert fetch.returncode == 0, fetch.stderr
    assert "AuthService.login" in fetch.stdout
    assert "10 | def login(user, pwd):" in fetch.stdout
    # fetch must surface the relationships preview and the drill-down hint
    assert "relationships (preview)" in fetch.stdout
    assert "outgoing_calls (5)" in fetch.stdout
    assert "Runs SQL" in fetch.stdout
    assert "relationships.py" in fetch.stdout

    assert chat.returncode == 0, chat.stderr
    assert "Auth is handled in AuthService." in chat.stdout
    assert "Conversation ID: conv_123" in chat.stdout

    assert [request["path"] for request in requests] == [
        "/api/datasources/ready",
        "/api/search?Query=auth&Mode=auto&IncludeContent=false&DescriptionDetail=Short&Names=backend",
        "/api/search/artifacts",
        "/api/chat/completions",
    ]


def test_relationships_script_works_against_mock_backend():
    def relationships_handler(request):
        body = json.loads(request["body"])
        assert body["identifier"] == "org/repo::src/svc.py::Service"
        assert body["profile"] == "CallsOnly"
        assert body["maxCountPerType"] == 50
        return 200, {
            "sourceIdentifier": body["identifier"],
            "profile": body["profile"],
            "found": True,
            "relationships": [
                {
                    "relationType": "OutgoingCalls",
                    "totalCount": 3,
                    "returnedCount": 3,
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
                },
                {
                    "relationType": "IncomingCalls",
                    "totalCount": 1,
                    "returnedCount": 1,
                    "truncated": False,
                    "items": [
                        {
                            "identifier": "org/repo::src/main.py::run",
                            "filePath": "src/main.py",
                            "startLine": 5,
                        }
                    ],
                },
            ],
        }, {}

    with mock_codealive_server(
        {("POST", "/api/search/artifact-relationships"): relationships_handler}
    ) as (base_url, requests):
        env = {
            **os.environ,
            "CODEALIVE_API_KEY": "skill-test-key",
            "CODEALIVE_BASE_URL": f"{base_url}/api",
        }

        result = _run("relationships.py", "org/repo::src/svc.py::Service", env=env)

    assert result.returncode == 0, result.stderr
    # Source identifier and profile in the header
    assert "org/repo::src/svc.py::Service" in result.stdout
    assert "callsOnly" in result.stdout
    # Both groups rendered with snake_case labels
    assert "outgoing_calls" in result.stdout
    assert "incoming_calls" in result.stdout
    # Items + locations + summaries
    assert "src/db.py:42" in result.stdout
    assert "Runs SQL" in result.stdout
    assert "src/main.py:5" in result.stdout
    # Single backend call
    assert [request["path"] for request in requests] == [
        "/api/search/artifact-relationships",
    ]


def test_relationships_script_emits_json_when_flag_set():
    def relationships_handler(_request):
        return 200, {
            "sourceIdentifier": "org/repo::Missing",
            "profile": "InheritanceOnly",
            "found": False,
        }, {}

    with mock_codealive_server(
        {("POST", "/api/search/artifact-relationships"): relationships_handler}
    ) as (base_url, _requests):
        env = {
            **os.environ,
            "CODEALIVE_API_KEY": "skill-test-key",
            "CODEALIVE_BASE_URL": f"{base_url}/api",
        }

        result = _run(
            "relationships.py",
            "org/repo::Missing",
            "--profile", "inheritanceOnly",
            "--json",
            env=env,
        )

    assert result.returncode == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["found"] is False
    assert parsed["sourceIdentifier"] == "org/repo::Missing"


def test_check_auth_hook_normalizes_base_url_and_uses_repo_root_fallback():
    script = REPO_ROOT / "hooks" / "scripts" / "check_auth.sh"
    env = {
        "PATH": "/usr/bin:/bin",
        "USER": "codealive-skills-test",
        "CODEALIVE_BASE_URL": "https://codealive.example.com/api",
    }

    result = subprocess.run(
        ["/bin/bash", str(script)],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "https://codealive.example.com/settings/api-keys" in result.stdout
    assert str(REPO_ROOT / "skills" / "codealive-context-engine" / "setup.py") in result.stdout
