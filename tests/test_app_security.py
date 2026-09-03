from __future__ import annotations

import time

from app.security import hash_password, read_session, sign_session, verify_password


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
