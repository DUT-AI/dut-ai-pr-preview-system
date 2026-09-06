from __future__ import annotations

import time

import pytest

from app.security import hash_password, read_session, sign_session, verify_password
from app.server.config import repository_is_allowed, validate_repository_scope


def test_password_hash_round_trip_and_wrong_password():
    encoded = hash_password("a demo password")
    assert "a demo password" not in encoded
    assert verify_password("a demo password", encoded)
    assert not verify_password("wrong", encoded)


def test_signed_session_rejects_tampering_and_expiry():
    token = sign_session("admin", "session-secret")
    assert read_session(token, "session-secret") == "admin"
    assert read_session(token + "x", "session-secret") is None
    expired = sign_session("admin", "session-secret", max_age=-1)
    time.sleep(0.01)
    assert read_session(expired, "session-secret") is None


def test_repository_scope_allows_exact_repo_or_one_owner_only():
    scopes = frozenset({"DUT-AI/*", "another-owner/one-repo"})

    assert repository_is_allowed("DUT-AI/first", scopes)
    assert repository_is_allowed("dut-ai/second", scopes)
    assert repository_is_allowed("another-owner/one-repo", scopes)
    assert not repository_is_allowed("another-owner/other-repo", scopes)
    assert not repository_is_allowed("DUT-AI/../outside", scopes)


@pytest.mark.parametrize(
    "scope",
    ["*", "*/repo", "DUT-AI/repo*", "DUT-AI/**", "DUT-AI/../*"],
)
def test_repository_scope_rejects_broad_or_malformed_wildcards(scope):
    with pytest.raises(ValueError):
        validate_repository_scope(scope)
