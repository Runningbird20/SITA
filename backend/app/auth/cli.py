"""Create the first user — the bootstrap step for enabling auth at all
(app.auth.service.any_users_exist is the single switch: zero User rows
means auth stays disabled). There's no open self-registration endpoint on
purpose (a locked-down security tool shouldn't let anyone sign themselves
up as admin), so the very first account has to be created this way; every
subsequent one can go through the real API (`POST /api/v1/auth/users`,
admin-only) once an admin exists to authorize it.

Usage:
    uv run python -m app.auth.cli create-user <username> <password> --role admin
"""

import argparse
import getpass
import sys

from app.auth.service import create_user
from app.db.session import SessionLocal
from app.models.enums import UserRole


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-user", help="Create a new user")
    create_parser.add_argument("username")
    create_parser.add_argument(
        "password",
        nargs="?",
        default=None,
        help="Omit to be prompted (doesn't echo, doesn't end up in shell history)",
    )
    create_parser.add_argument(
        "--role", choices=[r.value for r in UserRole], default=UserRole.ANALYST.value
    )

    args = parser.parse_args(argv)
    password = args.password or getpass.getpass("Password: ")

    db = SessionLocal()
    try:
        create_user(db, args.username, password, UserRole(args.role))
        db.commit()
    finally:
        db.close()

    print(f"Created user {args.username!r} (role={args.role})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
