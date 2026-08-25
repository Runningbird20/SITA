"""Shared validation helpers and the IngestionAdapter base class.

Per DEF.md § Phase 2 §3: every adapter validates *shape* (required fields
present, correct type, enum values in range) — never semantic/threat
meaning. An adapter never raises for a malformed record in a way that
escapes as an unhandled exception from the ingestion service; it always
raises `IngestionValidationError`, which the service catches per-record.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

from app.models.enums import SourceType
from app.schemas.ingestion import ParsedEvent


class IngestionValidationError(Exception):
    """Raised by an adapter when a raw record fails shape validation.
    Carries enough detail to populate one IngestionReport.errors entry.
    """

    def __init__(self, reason: str, field: str | None = None):
        self.reason = reason
        self.field = field
        super().__init__(reason)


def require_field(raw: dict, field: str):
    if field not in raw or raw[field] is None:
        raise IngestionValidationError(f"missing required field: {field}", field=field)
    return raw[field]


def require_str(raw: dict, field: str) -> str:
    value = require_field(raw, field)
    if not isinstance(value, str) or not value:
        raise IngestionValidationError(f"field must be a non-empty string: {field}", field=field)
    return value


def require_int(raw: dict, field: str) -> int:
    value = require_field(raw, field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise IngestionValidationError(f"field must be an integer: {field}", field=field)
    return value


def require_enum(raw: dict, field: str, allowed: set[str]) -> str:
    value = require_str(raw, field)
    if value not in allowed:
        raise IngestionValidationError(
            f"field {field} must be one of {sorted(allowed)}, got {value!r}", field=field
        )
    return value


def optional_str(raw: dict, field: str) -> str | None:
    value = raw.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise IngestionValidationError(f"field must be a string: {field}", field=field)
    return value


def optional_int(raw: dict, field: str) -> int | None:
    value = raw.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise IngestionValidationError(f"field must be an integer: {field}", field=field)
    return value


def parse_timestamp(raw: dict) -> datetime:
    value = require_field(raw, "timestamp")
    if not isinstance(value, str):
        raise IngestionValidationError(
            "field must be an ISO 8601 string: timestamp", field="timestamp"
        )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IngestionValidationError(
            f"unparseable timestamp: {value!r}", field="timestamp"
        ) from exc


class IngestionAdapter(ABC):
    """One per source type. `parse()` handles the universal fields
    (`timestamp`, `host`) that every source type shares, then delegates to
    `normalize()` for the source-type-specific mapping.
    """

    source_type: ClassVar[SourceType]

    def parse(self, raw: dict) -> ParsedEvent:
        occurred_at = parse_timestamp(raw)
        host = require_str(raw, "host")
        normalized = self.normalize(raw)
        return ParsedEvent(
            source_type=self.source_type,
            occurred_at=occurred_at,
            source_host=host,
            raw_payload=raw,
            normalized=normalized,
        )

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """Validate and map source-type-specific fields into the
        normalized shape defined in DEF.md § Phase 2 §2. `raw["host"]` is
        already guaranteed present and non-empty by `parse()` above by the
        time this runs.
        """
