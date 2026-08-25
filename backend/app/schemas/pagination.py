from pydantic import BaseModel


class Page[T](BaseModel):
    """The one envelope every list endpoint returns. See DEF.md § Phase 9."""

    items: list[T]
    total: int
    limit: int
    offset: int
