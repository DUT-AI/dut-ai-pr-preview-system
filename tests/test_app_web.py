from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.server.config import ServerConfig
from app.server.controller import create_app
from app.security import hash_password


class Store:
    def migrate(self): pass
    def health(self): return True
    def list_repositories(self):
        return [{
            "owner": "DUT-AI", "name": "dut-ai-pr-preview-system",
            "full_name": "DUT-AI/dut-ai-pr-preview-system",
            "pull_request_count": 1, "run_count": 1, "active_job_count": 0,
            "default_branch": "main",
        }]

    def repository_detail(self, full_name):
        return {
            "repository": {"full_name": full_name},
            "pull_requests": [],
            "jobs": [{
                "id": 8, "pr_number": 9, "head_sha": "a" * 40,
                "status": "running", "attempt": 1, "error": None,
            }],
        }


class GitHub:
    pass


def config() -> ServerConfig:
    return ServerConfig(
        database_url="postgresql://unused", github_app_id="1",
        github_installation_id=42, github_private_key_path=Path("unused.pem"),
        github_webhook_secret="hook",
        allowed_repositories=frozenset({"DUT-AI/dut-ai-pr-preview-system"}),
        admin_username="admin", admin_password_hash=hash_password("test-pass"),
        session_secret="session-secret", session_secure=False,
        llm_base_url="https://llm2.dutai.site/v1", llm_model="model",
        llm_api_key="", publish_enabled=False, session_root=Path("sessions"),
    )


def test_login_protects_dashboard_and_uses_csrf():
    client = TestClient(create_app(config(), Store(), GitHub()))
    landing = client.get("/")
    assert landing.status_code == 200
    assert "He thong PR Review cua CLB" in landing.text
    assert 'href="/login"' in landing.text
    assert client.get("/dashboard").status_code == 401
    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)

    bad = client.post("/login", data={
        "csrf": csrf, "username": "admin", "password": "wrong",
    })
    assert bad.status_code == 401

    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    logged_in = client.post("/login", data={
        "csrf": csrf, "username": "admin", "password": "test-pass",
    }, follow_redirects=False)
    assert logged_in.status_code == 303
    assert logged_in.headers["location"] == "/dashboard"
    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert "DUT-AI" in dashboard.text
    assert "Preview only" in dashboard.text


def test_login_rejects_missing_csrf():
    client = TestClient(create_app(config(), Store(), GitHub()))
    assert client.post("/login", data={
        "username": "admin", "password": "test-pass",
    }).status_code == 403


def test_repository_page_shows_pipeline_job_status():
    client = TestClient(create_app(config(), Store(), GitHub()))
    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    client.post("/login", data={
        "csrf": csrf, "username": "admin", "password": "test-pass",
    })

    response = client.get(
        "/repositories/DUT-AI/dut-ai-pr-preview-system"
    )
    assert response.status_code == 200
    assert "Trạng thái pipeline" in response.text
    assert "running" in response.text
