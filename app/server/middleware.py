"""Request security helpers shared by HTML and API controllers."""
from __future__ import annotations

import hmac
from urllib.parse import parse_qs

from fastapi import HTTPException, Request

from app.security import new_csrf_token, read_session, sign_session

SESSION_COOKIE = "dut_ai_session"
CSRF_COOKIE = "dut_ai_csrf"


def current_user(request: Request, config) -> str | None:
    username = read_session(
        request.cookies.get(SESSION_COOKIE, ""), config.session_secret
    )
    return username if username == config.admin_username else None


def require_user(request: Request, config) -> str:
    username = current_user(request, config)
    if username is None:
        raise HTTPException(status_code=401, detail="login required")
    return username


def set_csrf_cookie(response, config, token: str | None = None) -> str:
    token = token or new_csrf_token()
    response.set_cookie(
        CSRF_COOKIE,
        sign_session("csrf:" + token, config.session_secret),
        httponly=True,
        secure=config.session_secure,
        samesite="strict",
        max_age=43_200,
    )
    return token


def check_csrf(request: Request, submitted: str, config) -> None:
    expected = read_session(
        request.cookies.get(CSRF_COOKIE, ""), config.session_secret
    )
    if not expected or not expected.startswith("csrf:"):
        raise HTTPException(status_code=403, detail="invalid CSRF token")
    if not hmac.compare_digest(expected[5:], submitted):
        raise HTTPException(status_code=403, detail="invalid CSRF token")


def set_login_cookie(response, config) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        sign_session(config.admin_username, config.session_secret),
        httponly=True,
        secure=config.session_secure,
        samesite="strict",
        max_age=43_200,
    )


async def form_values(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8", errors="strict")
    values = parse_qs(body, keep_blank_values=True)
    return {key: items[-1] for key, items in values.items()}
