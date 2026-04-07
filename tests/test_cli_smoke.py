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
                    "identifier": "org/repo::src/auth.py::AuthService",
                    "content": "class AuthService:\n    pass\n",
                    "startLine": 10,
                    "contentByteSize": 28,
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
        fetch = _run("fetch.py", "org/repo::src/auth.py::AuthService", env=env)
        chat = _run("chat.py", "How does auth work?", "backend", env=env)

    assert datasources.returncode == 0, datasources.stderr
    assert json.loads(datasources.stdout)[0]["name"] == "backend"

    assert search.returncode == 0, search.stderr
    assert "src/auth.py:10-20" in search.stdout
    assert "Handles auth" in search.stdout

    assert fetch.returncode == 0, fetch.stderr
    assert "AuthService" in fetch.stdout
    assert "10 | class AuthService:" in fetch.stdout

    assert chat.returncode == 0, chat.stderr
    assert "Auth is handled in AuthService." in chat.stdout
    assert "Conversation ID: conv_123" in chat.stdout

    assert [request["path"] for request in requests] == [
        "/api/datasources/ready",
        "/api/search?Query=auth&Mode=auto&IncludeContent=false&DescriptionDetail=Short&Names=backend",
        "/api/search/artifacts",
        "/api/chat/completions",
    ]


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
