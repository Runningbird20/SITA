from datetime import UTC, datetime


def as_aware_utc(value: datetime) -> datetime:
    """SQLite doesn't preserve tzinfo through a flush/refresh round-trip
    (unlike Postgres's TIMESTAMPTZ) — a naive value read back is always UTC
    by this project's convention, so treat it as such rather than let a
    naive/aware comparison raise.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
