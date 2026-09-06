"""HTTP controllers. Application construction lives in app.main."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.security import new_csrf_token, verify_password
from app.server.config import validate_repo
from app.server.middleware import check_csrf, current_user, form_values
from app.server.middleware import require_user, set_csrf_cookie, set_login_cookie
from app.server.services import ingest_webhook, publish_run

BASE = Path(__file__).resolve().parents[1] / "ui"
templates = Jinja2Templates(directory=str(BASE / "templates"))


def create_app(config=None, store=None, github=None):
    """Compatibility wrapper; the composition root remains app.main."""
    from app.main import create_app as factory

    return factory(config, store, github)


def create_router(config, store, github) -> APIRouter:
    router = APIRouter()

    @router.get("/healthz")
    def healthz():
        return {"status": "ok" if store.health() else "unavailable"}

    @router.post("/webhooks/github")
    async def github_webhook(request: Request):
        try:
            result = ingest_webhook(await request.body(), request.headers, config, store)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(result, status_code=202 if result.get("queued") else 200)

    @router.get("/", response_class=HTMLResponse)
    def landing(request: Request):
        return templates.TemplateResponse(
            request, "landing.html", {"current_user": current_user(request, config)}
        )

    @router.get("/login", response_class=HTMLResponse)
    def login_page(request: Request):
        if current_user(request, config):
            return RedirectResponse("/dashboard", status_code=303)
        token = new_csrf_token()
        response = templates.TemplateResponse(
            request, "login.html", {"username": config.admin_username, "csrf": token}
        )
        set_csrf_cookie(response, config, token)
        return response

    @router.post("/login")
    async def login(request: Request):
        form = await form_values(request)
        check_csrf(request, form.get("csrf", ""), config)
        valid = (
            form.get("username", "") == config.admin_username
            and verify_password(form.get("password", ""), config.admin_password_hash)
        )
        if not valid:
            raise HTTPException(status_code=401, detail="invalid credentials")
        response = RedirectResponse("/dashboard", status_code=303)
        set_login_cookie(response, config)
        set_csrf_cookie(response, config)
        return response

    @router.post("/logout")
    async def logout(request: Request):
        require_user(request, config)
        form = await form_values(request)
        check_csrf(request, form.get("csrf", ""), config)
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("dut_ai_session")
        response.delete_cookie("dut_ai_csrf")
        return response

    def page(request: Request, template: str, context: dict):
        token = new_csrf_token()
        response = templates.TemplateResponse(request, template, {**context, "csrf": token})
        set_csrf_cookie(response, config, token)
        return response

    @router.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request):
        require_user(request, config)
        return page(
            request,
            "index.html",
            {"repositories": store.list_repositories(), "publish_enabled": config.publish_enabled},
        )

    @router.get("/repositories/{owner}/{repo}", response_class=HTMLResponse)
    def repository_page(request: Request, owner: str, repo: str):
        require_user(request, config)
        try:
            full_name = validate_repo(f"{owner}/{repo}")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="repository not found") from exc
        if full_name not in config.allowed_repositories:
            raise HTTPException(status_code=404, detail="repository not found")
        detail = store.repository_detail(full_name)
        if detail is None:
            raise HTTPException(status_code=404, detail="repository not found")
        return page(request, "repository.html", {**detail, "publish_enabled": config.publish_enabled})

    @router.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: int):
        require_user(request, config)
        detail = store.run_detail(run_id)
        if detail is None or detail["run"]["repository"] not in config.allowed_repositories:
            raise HTTPException(status_code=404, detail="run not found")
        return page(request, "run.html", {**detail, "publish_enabled": config.publish_enabled})

    @router.post("/runs/{run_id}/publish")
    async def publish(request: Request, run_id: int):
        require_user(request, config)
        form = await form_values(request)
        check_csrf(request, form.get("csrf", ""), config)
        try:
            publish_run(config, store, github, run_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    @router.get("/api/repositories")
    def api_repositories(request: Request):
        require_user(request, config)
        return store.list_repositories()

    return router
