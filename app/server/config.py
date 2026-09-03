"""Trusted server configuration read only from the process environment."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def validate_repo(value: str) -> str:
    value = value.strip()
    if not _REPO_RE.fullmatch(value) or ".." in value:
        raise ValueError(f"invalid owner/repository: {value!r}")
    return value


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


@dataclass(frozen=True)
class ServerConfig:
    database_url: str
    github_app_id: str
    github_installation_id: int
    github_private_key_path: Path
    github_webhook_secret: str
    allowed_repositories: frozenset[str]
    admin_username: str
    admin_password_hash: str
    session_secret: str
    session_secure: bool
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    publish_enabled: bool
    session_root: Path


def load_server_config() -> ServerConfig:
    repositories = frozenset(
        validate_repo(item)
        for item in os.environ.get(
            "GITHUB_ALLOWED_REPOSITORIES",
            "DUT-AI/dut-ai-pr-preview-system",
        ).split(",")
        if item.strip()
    )
    if not repositories:
        raise RuntimeError("GITHUB_ALLOWED_REPOSITORIES cannot be empty")
    installation = _required("GITHUB_INSTALLATION_ID")
    try:
        installation_id = int(installation)
    except ValueError as exc:
        raise RuntimeError("GITHUB_INSTALLATION_ID must be an integer") from exc
    return ServerConfig(
        database_url=_required("DATABASE_URL"),
        github_app_id=_required("GITHUB_APP_ID"),
        github_installation_id=installation_id,
        github_private_key_path=Path(_required("GITHUB_PRIVATE_KEY_PATH")).resolve(),
        github_webhook_secret=_required("GITHUB_WEBHOOK_SECRET"),
        allowed_repositories=repositories,
        admin_username=os.environ.get("ADMIN_USERNAME", "admin").strip() or "admin",
        admin_password_hash=_required("ADMIN_PASSWORD_HASH"),
        session_secret=_required("SESSION_SECRET"),
        session_secure=os.environ.get("SESSION_COOKIE_SECURE", "true").lower()
        not in {"0", "false", "no"},
        llm_base_url=os.environ.get(
            "LLM_BASE_URL", "https://llm2.dutai.site/v1"
        ).rstrip("/"),
        llm_model=os.environ.get(
            "LLM_MODEL", "ggml-org/gemma-4-e4b-it-GGUF:Q4_0"
        ),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        publish_enabled=os.environ.get("PUBLISH_ENABLED", "false").lower()
        in {"1", "true", "yes"},
        session_root=Path(os.environ.get("DSH_SESSION_ROOT", "/data/sessions")).resolve(),
    )
