"""Generate an ADMIN_PASSWORD_HASH without putting a password in source."""
from __future__ import annotations

import getpass

from app.security import hash_password


def main() -> None:
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if not password or password != confirmation:
        raise SystemExit("passwords do not match or are empty")
    print(hash_password(password))


if __name__ == "__main__":
    main()
