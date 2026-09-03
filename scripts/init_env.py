"""Create the ignored Docker .env without printing generated secrets."""
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Create local Docker secrets")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if TARGET.exists() and not args.force:
        print(f"{TARGET} already exists; left unchanged")
        return 0

    postgres_password = os.environ.get("POSTGRES_PASSWORD") or secrets.token_hex(24)
    admin_password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(18)
    values = {
        "POSTGRES_PASSWORD": postgres_password,
        "GITHUB_APP_ID": os.environ.get("GITHUB_APP_ID", "REPLACE_WITH_GITHUB_APP_ID"),
        "GITHUB_INSTALLATION_ID": os.environ.get(
            "GITHUB_INSTALLATION_ID", "REPLACE_WITH_GITHUB_INSTALLATION_ID"
        ),
        "GITHUB_PRIVATE_KEY_FILE": os.environ.get(
            "GITHUB_PRIVATE_KEY_FILE", "./secrets/github-app.pem"
        ),
        "GITHUB_WEBHOOK_SECRET": os.environ.get(
            "GITHUB_WEBHOOK_SECRET", secrets.token_urlsafe(48)
        ),
        # Stored locally so the generated login can be recovered from .env.
        # Compose passes only ADMIN_PASSWORD_HASH to the application container.
        "ADMIN_PASSWORD": admin_password,
        "ADMIN_PASSWORD_HASH": os.environ.get(
            "ADMIN_PASSWORD_HASH", hash_password(admin_password)
        ),
        "SESSION_SECRET": os.environ.get(
            "SESSION_SECRET", secrets.token_urlsafe(48)
        ),
    }
    lines = [
        "# Generated local runtime configuration. Never commit this file.",
        "# Required values only. Docker supplies internal paths and safe defaults.",
        "",
    ]
    lines.extend(f"{name}={_quoted(value)}" for name, value in values.items())
    TARGET.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Created {TARGET}")
    print("Generated DB, admin, webhook, and session secrets without displaying them.")
    print("GitHub App ID, installation ID, and private-key PEM still require GitHub.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
