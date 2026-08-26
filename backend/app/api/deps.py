"""Shared dependencies and helpers used across every resource router:
pagination params and the whitelisted-sort-field validator. See DEF.md §
Phase 9.
"""

import hmac
from dataclasses import dataclass

from fastapi import Header, Query
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute

from app.core.config import get_settings
from app.core.exceptions import InvalidQueryParameterError, UnauthorizedError


@dataclass
class PageParams:
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(50, ge=1, le=200, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def require_auth(authorization: str | None = Header(None)) -> None:
    """Dependency added to every /api/v1/* router. See DEF.md § Phase 14.

    A no-op when settings.api_auth_token is unset (the default) — auth is
    opt-in, not mandatory-on, so every existing quick-start command and
    test keeps working with no Authorization header at all. When a token
    is configured, requires `Authorization: Bearer <token>` matching
    exactly (constant-time compare — a token is a real secret, not just a
    feature flag).
    """
    token = get_settings().api_auth_token
    if not token:
        return
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError()
    presented = authorization.removeprefix("Bearer ")
    if not hmac.compare_digest(presented, token):
        raise UnauthorizedError()


def apply_sort[T](
    stmt: Select[T],
    sort: str | None,
    allowed: dict[str, InstrumentedAttribute],
    default: str,
) -> Select[T]:
    """`sort` is a bare field name (ascending) or `-field` (descending),
    validated against `allowed` — never every column, never raw input
    reaching ORDER BY unchecked. Raises InvalidQueryParameterError (→ 422)
    for an unlisted field.
    """
    raw = sort if sort is not None else default
    descending = raw.startswith("-")
    field = raw[1:] if descending else raw

    column = allowed.get(field)
    if column is None:
        raise InvalidQueryParameterError(
            f"invalid sort field {field!r}; allowed: {sorted(allowed)}"
        )
    return stmt.order_by(column.desc() if descending else column.asc())
