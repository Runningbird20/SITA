"""User/session persistence — create users, authenticate, issue/resolve/
revoke session tokens. See DEF.md § Phase 14, "Multi-user / RBAC
(post-roadmap)".
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.security import generate_token, hash_password, hash_token, verify_password
from app.core.time import as_aware_utc
from app.models.auth_token import AuthToken
from app.models.enums import UserRole
from app.models.user import User


def any_users_exist(db: Session) -> bool:
    """The single switch for whether auth is enabled at all — see
    Settings.auth_token_expiry_days's docstring in app/core/config.py.
    """
    return db.scalars(select(User.id).limit(1)).first() is not None


def create_user(db: Session, username: str, password: str, role: UserRole) -> User:
    user = User(username=username, password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalars(select(User).where(User.username == username)).first()
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def issue_token(db: Session, user: User, expiry_days: int) -> tuple[str, AuthToken]:
    """Returns (raw_token, row) — raw_token is the only time the actual
    bearer value ever exists outside the client; only its hash is
    persisted (see app/auth/security.py::hash_token).
    """
    raw_token = generate_token()
    token_row = AuthToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=datetime.now(UTC) + timedelta(days=expiry_days),
    )
    db.add(token_row)
    db.flush()
    return raw_token, token_row


def resolve_token(db: Session, raw_token: str) -> User | None:
    token_row = db.scalars(
        select(AuthToken).where(AuthToken.token_hash == hash_token(raw_token))
    ).first()
    if token_row is None or as_aware_utc(token_row.expires_at) < datetime.now(UTC):
        return None
    return db.get(User, token_row.user_id)


def revoke_token(db: Session, raw_token: str) -> None:
    db.execute(delete(AuthToken).where(AuthToken.token_hash == hash_token(raw_token)))
