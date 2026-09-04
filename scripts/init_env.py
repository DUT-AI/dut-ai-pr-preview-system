"""Create or expand the ignored Docker .env without printing secrets."""
from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / ".env"
sys.path.insert(0, str(ROOT))

from app.security import hash_password  # noqa: E402


def _quoted(value: str) -> str:
    """Single quotes keep Compose from expanding '$' in password hashes."""
    return "'" + value.replace("'", "\\'") + "'"


def _read_existing(path: Path) -> dict[str, str]:
    """Read values written by this script so an update keeps current secrets."""
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if value.startswith("'") and value.endswith("'"):
            value = value[1:-1].replace("\\'", "'")
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        values[name] = value
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Create local Docker secrets")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--update",
        action="store_true",
        help="keep existing values and add all current settings",
    )
    args = parser.parse_args()
    if args.force and args.update:
        parser.error("--force and --update cannot be used together")
    if TARGET.exists() and not args.force and not args.update:
        print(f"{TARGET} already exists; left unchanged")
        return 0

    existing = _read_existing(TARGET) if args.update else {}

    def setting(name: str, default: str) -> str:
        return existing.get(name) or os.environ.get(name) or default

    postgres_password = setting("POSTGRES_PASSWORD", secrets.token_hex(24))
    admin_password = setting("ADMIN_PASSWORD", secrets.token_urlsafe(18))
    admin_password_hash = setting("ADMIN_PASSWORD_HASH", "")
    if not admin_password_hash:
        admin_password_hash = hash_password(admin_password)
    sections = [
        (
            "DOCKER COMPOSE",
            [
                ("COMPOSE_PROJECT_NAME", setting("COMPOSE_PROJECT_NAME", "dut-ai-pr-preview")),
            ],
        ),
        (
            "POSTGRESQL DATABASE",
            [
                ("POSTGRES_IMAGE", setting("POSTGRES_IMAGE", "postgres:16-alpine")),
                ("POSTGRES_DB", setting("POSTGRES_DB", "dut_ai_pr_preview")),
                ("POSTGRES_USER", setting("POSTGRES_USER", "dut_ai")),
                ("POSTGRES_PASSWORD", postgres_password),
                ("POSTGRES_HOST", setting("POSTGRES_HOST", "dut-ai-pr-preview-postgres")),
                ("POSTGRES_BIND_HOST", setting("POSTGRES_BIND_HOST", "127.0.0.1")),
                ("POSTGRES_EXTERNAL_PORT", setting("POSTGRES_EXTERNAL_PORT", "5433")),
                ("POSTGRES_INTERNAL_PORT", setting("POSTGRES_INTERNAL_PORT", "5432")),
            ],
        ),
        (
            "WEB UI / API",
            [
                ("WEB_BIND_HOST", setting("WEB_BIND_HOST", "127.0.0.1")),
                ("WEB_EXTERNAL_PORT", setting("WEB_EXTERNAL_PORT", "8000")),
                ("WEB_INTERNAL_PORT", setting("WEB_INTERNAL_PORT", "8000")),
            ],
        ),
        (
            "ADMIN AUTH / SESSION SIGNING",
            [
                ("ADMIN_USERNAME", setting("ADMIN_USERNAME", "admin")),
                # Kept locally for recovery; Compose does not pass it to the app.
                ("ADMIN_PASSWORD", admin_password),
                ("ADMIN_PASSWORD_HASH", admin_password_hash),
                ("SESSION_SECRET", setting("SESSION_SECRET", secrets.token_urlsafe(48))),
                ("SESSION_COOKIE_SECURE", setting("SESSION_COOKIE_SECURE", "true")),
            ],
        ),
        (
            "GITHUB APP / JWT / WEBHOOK",
            [
                ("GITHUB_APP_ID", setting(
                    "GITHUB_APP_ID", "REPLACE_WITH_GITHUB_APP_ID"
                )),
                ("GITHUB_INSTALLATION_ID", setting(
                    "GITHUB_INSTALLATION_ID", "REPLACE_WITH_GITHUB_INSTALLATION_ID"
                )),
                ("GITHUB_ALLOWED_REPOSITORIES", setting(
                    "GITHUB_ALLOWED_REPOSITORIES",
                    "DUT-AI/dut-ai-pr-preview-system",
                )),
                ("GITHUB_PRIVATE_KEY_FILE", setting(
                    "GITHUB_PRIVATE_KEY_FILE", "./secrets/github-app.pem"
                )),
                ("GITHUB_PRIVATE_KEY_PATH", setting(
                    "GITHUB_PRIVATE_KEY_PATH", "/run/secrets/github-app.pem"
                )),
                ("GITHUB_WEBHOOK_SECRET", setting(
                    "GITHUB_WEBHOOK_SECRET", secrets.token_urlsafe(48)
                )),
            ],
        ),
        (
            "LLM PROVIDER",
            [
                ("LLM_BASE_URL", setting(
                    "LLM_BASE_URL", "https://llm2.dutai.site/v1"
                )),
                ("LLM_MODEL", setting(
                    "LLM_MODEL", "ggml-org/gemma-4-e4b-it-GGUF:Q4_0"
                )),
                ("LLM_API_KEY", setting("LLM_API_KEY", "")),
            ],
        ),
        (
            "REVIEW POLICY / STORAGE",
            [
                ("PUBLISH_ENABLED", setting("PUBLISH_ENABLED", "false")),
                ("DSH_SESSION_ROOT", setting("DSH_SESSION_ROOT", "/data/sessions")),
            ],
        ),
    ]
    managed_names = {
        name for _title, values in sections for name, _value in values
    }
    extra_values = [
        (name, value)
        for name, value in existing.items()
        if name not in managed_names
    ]
    if extra_values:
        sections.append(("EXTRA EXISTING SETTINGS", sorted(extra_values)))
    lines = [
        "# Generated local runtime configuration. Never commit this file.",
        "# Run `python scripts/init_env.py --update` after pulling config changes.",
    ]
    for title, values in sections:
        lines.extend(["", "# " + "-" * 77, f"# {title}", "# " + "-" * 77])
        lines.extend(f"{name}={_quoted(value)}" for name, value in values)
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    action = "Updated" if existing else "Created"
    print(f"{action} {TARGET}")
    print("All values were written without displaying secrets.")
    print("Review GitHub IDs and both host/container port settings before deployment.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
