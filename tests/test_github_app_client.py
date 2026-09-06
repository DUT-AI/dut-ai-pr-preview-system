from __future__ import annotations

import json
import base64
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.server.config import ServerConfig
from app.server.repositories import GitHubAppClient
from src.synthesize import MARKER


def _decode_segment(value: str) -> dict:
    value += "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(value))


def config() -> ServerConfig:
    return ServerConfig(
        database_url="postgresql://unused", github_app_id="1",
        github_installation_id=42, github_private_key_path=Path("unused.pem"),
        github_webhook_secret="hook",
        allowed_repositories=frozenset({"DUT-AI/dut-ai-pr-preview-system"}),
        admin_username="admin", admin_password_hash="unused",
        session_secret="session", session_secure=False,
        llm_base_url="https://llm2.dutai.site/v1", llm_model="model",
        llm_api_key="", publish_enabled=True, session_root=Path("sessions"),
    )


def test_app_jwt_uses_short_github_compatible_lifetime(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "app.pem"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    configured = replace(config(), github_private_key_path=key_path)
    monkeypatch.setattr("app.server.repositories.time.time", lambda: 1_000)

    token = GitHubAppClient(configured)._app_jwt()
    header, payload, signature = token.split(".")

    assert _decode_segment(header) == {"alg": "RS256", "typ": "JWT"}
    assert _decode_segment(payload) == {"iat": 970, "exp": 1_300, "iss": "1"}
    assert signature


def test_installation_uses_app_jwt_instead_of_installation_token(monkeypatch):
    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert request.url.path == "/app/installations/42"
        assert request.headers["Authorization"] == "Bearer app-jwt"
        return httpx.Response(200, json={"id": 42})

    client = GitHubAppClient(config(), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client, "_app_jwt", lambda: "app-jwt")
    monkeypatch.setattr(
        client,
        "installation_token",
        lambda: pytest.fail("installation token must not authenticate this endpoint"),
    )

    assert client.installation() == {"id": 42}


def test_repositories_support_owner_scope_and_pagination(monkeypatch):
    pages = []

    def handler(request: httpx.Request):
        assert request.url.path == "/installation/repositories"
        page = int(request.url.params["page"])
        pages.append(page)
        if page == 1:
            repositories = [
                {"full_name": f"DUT-AI/repository-{number}"}
                for number in range(100)
            ]
        else:
            repositories = [
                {"full_name": "DUT-AI/final-repository"},
                {"full_name": "outside/not-allowed"},
            ]
        return httpx.Response(200, json={"repositories": repositories})

    configured = replace(
        config(), allowed_repositories=frozenset({"DUT-AI/*"})
    )
    client = GitHubAppClient(configured, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client, "installation_token", lambda: "installation-token")

    repositories = client.repositories()

    assert pages == [1, 2]
    assert len(repositories) == 101
    assert repositories[-1]["full_name"] == "DUT-AI/final-repository"


def test_request_reports_github_error_without_exposing_token(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(
            403,
            headers={"X-Accepted-GitHub-Permissions": "issues=write"},
            json={"message": "Repository interaction is limited"},
        )

    client = GitHubAppClient(config(), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client, "installation_token", lambda: "secret-token")

    with pytest.raises(RuntimeError) as error:
        client._request("POST", "/repos/o/r/issues/1/comments", json={"body": "x"})

    message = str(error.value)
    assert "403" in message
    assert "Repository interaction is limited" in message
    assert "issues=write" in message
    assert "secret-token" not in message


def test_publish_updates_legacy_marker_and_reads_back(monkeypatch):
    requests = []
    body = "preview\n" + MARKER

    def handler(request: httpx.Request):
        requests.append((request.method, request.url.path))
        if request.url.path.endswith("/pulls/7"):
            return httpx.Response(200, json={"head": {"sha": "a" * 40}})
        if request.url.path.endswith("/issues/7/comments"):
            return httpx.Response(200, json=[{"id": 9, "body": "old " + MARKER}])
        if request.method == "PATCH":
            assert json.loads(request.content)["body"] == body
            return httpx.Response(200, json={"id": 9, "body": body,
                                             "html_url": "https://example/9"})
        if request.url.path.endswith("/issues/comments/9"):
            return httpx.Response(200, json={"id": 9, "body": body})
        raise AssertionError(request.url)

    client = GitHubAppClient(config(), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client, "installation_token", lambda: "installation-token")
    result = client.publish_preview(
        "DUT-AI/dut-ai-pr-preview-system", 7, "a" * 40, body
    )
    assert result["action"] == "updated"
    assert requests[-1] == ("GET", "/repos/DUT-AI/dut-ai-pr-preview-system/issues/comments/9")


def test_publish_rejects_stale_run_before_writing(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(200, json={"head": {"sha": "b" * 40}})

    client = GitHubAppClient(config(), transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client, "installation_token", lambda: "installation-token")
    with pytest.raises(RuntimeError, match="stale review"):
        client.publish_preview(
            "DUT-AI/dut-ai-pr-preview-system", 7, "a" * 40, "preview"
        )
