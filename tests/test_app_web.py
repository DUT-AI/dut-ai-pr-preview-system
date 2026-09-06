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
            "repository": {
                "full_name": full_name, "owner": "DUT-AI",
                "name": "dut-ai-pr-preview-system",
                "default_branch": "main",
            },
            "pull_requests": [{
                "number": 9, "title": "Improve dashboard", "author": "duytoan",
                "head_ref": "dev", "base_ref": "main", "head_sha": "a" * 40,
                "additions": 40, "deletions": 3, "latest_run_id": 7,
                "latest_run_status": "complete", "run_count": 2,
            }],
            "jobs": [{
                "id": 8, "pr_number": 9, "head_sha": "a" * 40,
                "status": "running", "attempt": 1, "error": None,
            }],
        }

    def pull_request_detail(self, full_name, pr_number):
        if pr_number != 9:
            return None
        return {
            "repository": {
                "full_name": full_name, "owner": "DUT-AI",
                "name": "dut-ai-pr-preview-system", "default_branch": "main",
            },
            "pull_request": {
                "number": 9, "title": "Improve dashboard", "author": "duytoan",
                "head_ref": "dev", "base_ref": "main", "head_sha": "a" * 40,
                "state": "open", "html_url": f"https://github.com/{full_name}/pull/9",
                "changed_files": 2, "additions": 40, "deletions": 3,
            },
            "runs": [{
                "id": 7, "head_sha": "a" * 40, "status": "complete",
                "created_at": "2026-09-06 10:00:00+00:00",
                "findings": {
                    "claims": [{"status": "PASS"}], "docs": [],
                    "impact": [], "threads": [], "unresolved_questions": [],
                },
                "comment_id": 12345,
            }, {
                "id": 6, "head_sha": "b" * 40, "status": "complete",
                "created_at": "2026-09-06 09:00:00+00:00",
                "findings": {"claims": [{"status": "FAIL"}]},
                "comment_id": None,
            }],
            "jobs": [{
                "id": 8, "pr_number": 9, "head_sha": "a" * 40,
                "status": "complete", "attempt": 1, "error": None,
                "created_at": "2026-09-06 09:59:00+00:00",
            }],
            "commits": [{
                "sha": "a" * 40, "message": "Improve UI",
            }],
        }

    def run_detail(self, run_id):
        if run_id != 7:
            return None
        return {
            "run": {
                "id": 7, "job_id": 8, "repository": "DUT-AI/dut-ai-pr-preview-system",
                "pr_number": 9, "head_sha": "a" * 40, "status": "complete",
                "created_at": "2026-09-06 10:00:00+00:00",
                "findings": {
                    "claims": [{
                        "id": "C1", "status": "PASS",
                        "evidence": ["app/ui/templates/run.html:1"],
                        "note": "Rendered safely <script>alert(1)</script>",
                    }],
                    "docs": [{
                        "path": "README.md", "status": "STALE",
                        "what": "Old dashboard copy",
                    }],
                    "impact": [{
                        "requirement": "Operator visibility", "impact": "CHANGED",
                        "detail": "Structured tables are visible",
                    }],
                    "threads": [{
                        "text": "Show the AI table", "status": "RESOLVED", "note": "Done",
                    }],
                    "unresolved_questions": [],
                },
                "report": "# Safe report\n<script>bad()</script>",
                "preview_comment": "## DUT AI review\n<table><script>bad()</script></table>",
            },
            "pr": {
                "title": "Improve dashboard", "body": "UI details",
                "html_url": "https://github.com/DUT-AI/dut-ai-pr-preview-system/pull/9",
                "changed_files": 2, "additions": 40, "deletions": 3,
                "files": [{
                    "filename": "app/ui/templates/run.html", "status": "modified",
                    "additions": 30, "deletions": 2,
                }],
            },
            "commits": [{"sha": "a" * 40, "message": "Improve UI"}],
            "publish_audit": [{
                "status": "success", "action": "update", "comment_id": 12345,
                "head_sha": "a" * 40, "error": None,
            }],
            "logs": [{
                "level": "info", "phase": "review", "message": "Review complete",
                "created_at": "2026-09-06 10:01:00+00:00",
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
    assert "Pull Request hệ thống đã nhận" in response.text
    assert "2 lần review" in response.text
    assert "/repositories/DUT-AI/dut-ai-pr-preview-system/pulls/9" in response.text
    assert "Trạng thái pipeline" in response.text
    assert "running" in response.text


def test_pull_request_page_shows_all_review_runs_and_navigation():
    client = TestClient(create_app(config(), Store(), GitHub()))
    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    client.post("/login", data={
        "csrf": csrf, "username": "admin", "password": "test-pass",
    })

    response = client.get(
        "/repositories/DUT-AI/dut-ai-pr-preview-system/pulls/9"
    )

    assert response.status_code == 200
    assert "Các lần AI đã review PR này" in response.text
    assert "RUN #7" in response.text
    assert "RUN #6" in response.text
    assert 'href="/runs/7"' in response.text
    assert 'href="/runs/6"' in response.text
    assert "PUBLISHED" in response.text
    assert "PREVIEW" in response.text
    assert "https://github.com/DUT-AI/dut-ai-pr-preview-system/pull/9" in response.text


def test_pull_request_page_rejects_invalid_or_unknown_number():
    client = TestClient(create_app(config(), Store(), GitHub()))
    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    client.post("/login", data={
        "csrf": csrf, "username": "admin", "password": "test-pass",
    })

    assert client.get(
        "/repositories/DUT-AI/dut-ai-pr-preview-system/pulls/0"
    ).status_code == 404
    assert client.get(
        "/repositories/DUT-AI/dut-ai-pr-preview-system/pulls/10"
    ).status_code == 404


def test_run_page_shows_structured_review_and_escaped_exact_preview():
    client = TestClient(create_app(config(), Store(), GitHub()))
    page = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
    client.post("/login", data={
        "csrf": csrf, "username": "admin", "password": "test-pass",
    })

    response = client.get("/runs/7")

    assert response.status_code == 200
    assert 'href="/repositories/DUT-AI/dut-ai-pr-preview-system/pulls/9"' in response.text
    assert "Bảng nhận xét của AI" in response.text
    assert "Nội dung comment GitHub nguyên bản" in response.text
    assert "app/ui/templates/run.html:1" in response.text
    assert "Rendered safely &lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "&lt;table&gt;&lt;script&gt;bad()&lt;/script&gt;&lt;/table&gt;" in response.text
    assert "<script>bad()</script>" not in response.text
    assert "https://github.com/DUT-AI/dut-ai-pr-preview-system/pull/9#issuecomment-12345" in response.text


def test_dashboard_summary_handles_missing_optional_counts():
    from app.server.presentation import dashboard_summary

    assert dashboard_summary([{"pull_request_count": 2}, {"run_count": 3}]) == {
        "repositories": 2, "pull_requests": 2, "runs": 3, "active_jobs": 0,
    }
