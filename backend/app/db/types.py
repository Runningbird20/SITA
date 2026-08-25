"""Dialect-portable column type helpers.

These are the only place a Postgres/SQLite difference is allowed to leak into
model definitions — every model imports from here instead of reaching for
dialect-specific types directly.
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres, plain JSON on SQLite (and anywhere else) — same Python
# interface (dict/list in, dict/list out) either way.
JSONVariant = JSON().with_variant(JSONB(), "postgresql")
