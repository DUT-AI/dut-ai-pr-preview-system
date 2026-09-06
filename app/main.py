"""DUT AI PR Preview web application entrypoint and composition root."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.server.config import ServerConfig, load_server_config
from app.server.controller import BASE, create_router
from app.server.github import GitHubAppClient
from app.server.repositories import PostgresStore


def create_app(config: ServerConfig | None = None, store=None, github=None) -> FastAPI:
    config = config or load_server_config()
    store = store or PostgresStore(config.database_url)
    github = github or GitHubAppClient(config)
    store.migrate()
    app = FastAPI(title="DUT AI PR Preview System")
    app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
    app.include_router(create_router(config, store, github))
    return app
