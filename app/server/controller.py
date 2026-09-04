from __future__ import annotations

import hmac
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.server.config import ServerConfig, load_server_config, validate_repo
from app.server.repositories import GitHubAppClient, PostgresStore
from app.server.services import ingest_webhook, publish_run
from app.security import new_csrf_token, read_session, sign_session, verify_password


BASE = Path(__file__).resolve().parents[1] / "ui"
templates = Jinja2Templates(directory=str(BASE / "templates"))
SESSION_COOKIE = "dut_ai_session"
CSRF_COOKIE = "dut_ai_csrf"


async def _form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8", errors="strict")
    values = parse_qs(body, keep_blank_values=True)
    return {key: items[-1] for key, items in values.items()}


def _user(request: Request, config: ServerConfig) -> str | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    username = read_session(token, config.session_secret)
    return username if username == config.admin_username else None


def _require_user(request: Request, config: ServerConfig) -> str:
    username = _user(request, config)
    if username is None:
        raise HTTPException(status_code=401, detail="login required")
    return username


def _check_csrf(request: Request, submitted: str, config: ServerConfig) -> None:
    signed = request.cookies.get(CSRF_COOKIE, "")
    expected = read_session(signed, config.session_secret)
    if not expected or not expected.startswith("csrf:"):
        raise HTTPException(status_code=403, detail="invalid CSRF token")
    if not hmac.compare_digest(expected[5:], submitted):
        raise HTTPException(status_code=403, detail="invalid CSRF token")


def _with_csrf(response, config: ServerConfig, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE, sign_session("csrf:" + token, config.session_secret),
        httponly=True, secure=config.session_secure, samesite="strict",
        max_age=43_200,
    )


def create_app(
    config: ServerConfig | None = None, store=None, github=None,
) -> FastAPI:
    config = config or load_server_config()
    store = store or PostgresStore(config.database_url)
    github = github or GitHubAppClient(config)
    store.migrate()

    app = FastAPI(title="DUT AI PR Preview System")
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok" if store.health() else "unavailable"}

    @app.post("/webhooks/github")
    async def github_webhook(request: Request):
        body = await request.body()
        try:
            result = ingest_webhook(body, request.headers, config, store)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result, status_code=202 if result.get("queued") else 200)

    @app.get("/", response_class=HTMLResponse)
    def landing(request: Request):
        return templates.TemplateResponse(request, "landing.html", {
            "current_user": _user(request, config),
        })

    @app.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if _user(request, config):
            return RedirectResponse("/dashboard", status_code=303)
        token = new_csrf_token()
        response = templates.TemplateResponse(request, "login.html", {
            "username": config.admin_username, "csrf": token,
        })
        _with_csrf(response, config, token)
        return response

    @app.post("/login")
    async def login(request: Request):
        form = await _form(request)
        _check_csrf(request, form.get("csrf", ""), config)
        valid = (
            hmac.compare_digest(form.get("username", ""), config.admin_username)
            and verify_password(form.get("password", ""), config.admin_password_hash)
        )
        if not valid:
            raise HTTPException(status_code=401, detail="invalid credentials")
        response = RedirectResponse("/dashboard", status_code=303)
        response.set_cookie(
            SESSION_COOKIE, sign_session(config.admin_username, config.session_secret),
            httponly=True, secure=config.session_secure, samesite="strict",
            max_age=43_200,
        )
        _with_csrf(response, config, new_csrf_token())
        return response

    @app.post("/logout")
    async def logout(request: Request):
        _require_user(request, config)
        form = await _form(request)
        _check_csrf(request, form.get("csrf", ""), config)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie(CSRF_COOKIE)
        return response

    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request):
        _require_user(request, config)
        token = new_csrf_token()
        response = templates.TemplateResponse(request, "index.html", {
            "repositories": store.list_repositories(), "csrf": token,
            "publish_enabled": config.publish_enabled,
        })
        _with_csrf(response, config, token)
        return response

    @app.get("/repositories/{owner}/{repo}", response_class=HTMLResponse)
    def repository_page(request: Request, owner: str, repo: str):
        _require_user(request, config)
        try:
            full_name = validate_repo(f"{owner}/{repo}")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="repository not found") from exc
        if full_name not in config.allowed_repositories:
            raise HTTPException(status_code=404, detail="repository not found")
        detail = store.repository_detail(full_name)
        if detail is None:
            raise HTTPException(status_code=404, detail="repository not found")
        token = new_csrf_token()
        response = templates.TemplateResponse(request, "repository.html", {
            **detail, "csrf": token, "publish_enabled": config.publish_enabled,
        })
        _with_csrf(response, config, token)
        return response

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: int):
        _require_user(request, config)
        detail = store.run_detail(run_id)
        if detail is None or detail["run"]["repository"] not in config.allowed_repositories:
            raise HTTPException(status_code=404, detail="run not found")
        token = new_csrf_token()
        response = templates.TemplateResponse(request, "run.html", {
            **detail, "csrf": token, "publish_enabled": config.publish_enabled,
        })
        _with_csrf(response, config, token)
        return response

    @app.post("/runs/{run_id}/publish")
    async def publish(request: Request, run_id: int):
        _require_user(request, config)
        form = await _form(request)
        _check_csrf(request, form.get("csrf", ""), config)
        try:
            publish_run(config, store, github, run_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    @app.get("/api/repositories")
    def api_repositories(request: Request):
        _require_user(request, config)
        return store.list_repositories()

    return app
