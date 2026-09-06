from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from app.server.config import ServerConfig, validate_repo
from app.server.services import ingest_webhook


class Store:
    def __init__(self):
        self.calls = []
        self.state_calls = []

    def record_delivery_and_enqueue(self, *args):
        self.calls.append(args)
        return len(self.calls) == 1

    def record_delivery_without_enqueue(self, *args):
        self.state_calls.append(args)
        return len(self.state_calls) == 1


def config() -> ServerConfig:
    return ServerConfig(
        database_url="postgresql://unused", github_app_id="1",
        github_installation_id=42, github_private_key_path=Path("unused.pem"),
        github_webhook_secret="hook-secret",
        allowed_repositories=frozenset({"DUT-AI/dut-ai-pr-preview-system"}),
        admin_username="admin", admin_password_hash="unused",
        session_secret="session-secret", session_secure=False,
        llm_base_url="https://llm2.dutai.site/v1", llm_model="model",
        llm_api_key="", publish_enabled=False, session_root=Path("sessions"),
    )


def signed_headers(body: bytes, *, delivery="delivery-1"):
    digest = hmac.new(b"hook-secret", body, hashlib.sha256).hexdigest()
    return {
        "x-hub-signature-256": "sha256=" + digest,
        "x-github-event": "pull_request", "x-github-delivery": delivery,
    }


def payload():
    return {
        "action": "opened", "installation": {"id": 42}, "number": 7,
        "repository": {"full_name": "DUT-AI/dut-ai-pr-preview-system"},
        "pull_request": {
            "title": "History UI", "body": "PR body",
            "user": {"login": "duytoan"},
            "base": {"ref": "main"},
            "head": {"ref": "dev", "sha": "a" * 40},
            "state": "open", "merged": False,
            "html_url": "https://github.com/DUT-AI/dut-ai-pr-preview-system/pull/7",
        },
    }


def test_webhook_verifies_signature_allowlist_and_deduplicates():
    body = json.dumps(payload()).encode()
    store = Store()
    first = ingest_webhook(body, signed_headers(body), config(), store)
    second = ingest_webhook(body, signed_headers(body), config(), store)
    assert first == {"accepted": True, "queued": True, "duplicate": False}
    assert second == {"accepted": True, "queued": False, "duplicate": True}


def test_webhook_rejects_bad_signature_before_parsing_payload():
    with pytest.raises(PermissionError, match="signature"):
        ingest_webhook(b"not json", {
            "x-hub-signature-256": "sha256=bad",
            "x-github-event": "pull_request", "x-github-delivery": "delivery-1",
        }, config(), Store())


def test_webhook_rejects_repository_outside_allowlist():
    data = payload()
    data["repository"]["full_name"] = "Other/repo"
    body = json.dumps(data).encode()
    with pytest.raises(PermissionError, match="allowlisted"):
        ingest_webhook(body, signed_headers(body), config(), Store())


def test_closed_webhook_updates_history_without_enqueuing_review():
    data = payload()
    data["action"] = "closed"
    data["pull_request"]["state"] = "closed"
    data["pull_request"]["merged"] = True
    body = json.dumps(data).encode()
    store = Store()

    first = ingest_webhook(body, signed_headers(body), config(), store)
    second = ingest_webhook(body, signed_headers(body), config(), store)

    assert first == {"accepted": True, "queued": False, "duplicate": False}
    assert second == {"accepted": True, "queued": False, "duplicate": True}
    assert store.calls == []
    assert len(store.state_calls) == 2
    assert store.state_calls[0][2] == "closed"


@pytest.mark.parametrize("value", ["../repo", "owner/../../repo", "one", "a/b/c"])
def test_repository_validation_rejects_paths(value):
    with pytest.raises(ValueError):
        validate_repo(value)
