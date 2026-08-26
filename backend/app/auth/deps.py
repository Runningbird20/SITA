"""FastAPI auth dependencies. See DEF.md § Phase 14, "Multi-user / RBAC
(post-roadmap)".

get_current_user is the one source of truth: None means auth is disabled
(no User rows exist — the zero-friction quick-start default, unchanged
from Phase 14's original single-token model); otherwise a valid session
token is required or UnauthorizedError (401) is raised. Router-level
`dependencies=[Depends(get_current_user)]` enforces this even for routes
that don't need the identity; routes that do (audit logging, role checks)
additionally declare it as a parameter — FastAPI's per-request dependency
cache means it only actually runs once either way.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.auth.service import any_users_exist, resolve_token
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.db.session import get_db
from app.models.enums import UserRole


@dataclass(frozen=True)
class CurrentUser:
    id: uuid.UUID
    username: str
    role: UserRole


def get_current_user(
    authorization: str | None = Header(None), db: Session = Depends(get_db)
) -> CurrentUser | None:
    if not any_users_exist(db):
        return None
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError()
    presented = authorization.removeprefix("Bearer ")
    user = resolve_token(db, presented)
    if user is None:
        raise UnauthorizedError()
    return CurrentUser(id=user.id, username=user.username, role=user.role)


def require_admin(
    current_user: CurrentUser | None = Depends(get_current_user),
) -> CurrentUser | None:
    """None (auth disabled) is allowed through, same as every other route
    — an admin-only route isn't more locked-down than the rest of the API
    when auth itself is off. Once auth is on, only UserRole.ADMIN passes.
    """
    if current_user is not None and current_user.role != UserRole.ADMIN:
        raise ForbiddenError()
    return current_user
