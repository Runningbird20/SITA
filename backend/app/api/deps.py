"""Shared dependencies and helpers used across every resource router:
pagination params and the whitelisted-sort-field validator. See DEF.md §
Phase 9. Auth dependencies live in app.auth.deps, not here — see DEF.md §
Phase 14, "Multi-user / RBAC (post-roadmap)".
"""

from dataclasses import dataclass

from fastapi import Query
from sqlalchemy import Select
from sqlalchemy.orm import InstrumentedAttribute

from app.core.exceptions import InvalidQueryParameterError


@dataclass
class PageParams:
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(50, ge=1, le=200, description="Max rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


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
