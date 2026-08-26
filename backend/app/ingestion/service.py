"""The shared ingestion path used by both the batch-import CLI and the
REST streaming endpoint (DEF.md § Phase 2 §4) — same validation, same
report shape, regardless of how the records arrived.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.metrics import events_ingested_total, ingestion_errors_total
from app.ingestion.base import IngestionValidationError
from app.ingestion.registry import get_adapter
from app.models.enums import SourceType
from app.models.event import SecurityEvent
from app.schemas.ingestion import IngestionReport, IngestionReportError

logger = logging.getLogger(__name__)


def ingest_records(
    db: Session,
    source_type: SourceType,
    raw_records: list[dict],
    batch_id: uuid.UUID | None = None,
) -> IngestionReport:
    """Validate and persist `raw_records` as SecurityEvent rows. Never
    raises for a malformed individual record — one bad record is recorded
    in the report's `errors` and does not stop the rest of the batch.

    Does not commit; the caller owns the transaction (the REST endpoint
    commits per-request, the CLI commits per-file).
    """
    adapter = get_adapter(source_type)
    errors: list[IngestionReportError] = []
    accepted = 0
    ingested_at = datetime.now(UTC)

    for index, raw in enumerate(raw_records):
        try:
            parsed = adapter.parse(raw)
        except IngestionValidationError as exc:
            errors.append(IngestionReportError(index=index, reason=exc.reason, field=exc.field))
            continue

        db.add(
            SecurityEvent(
                source_type=parsed.source_type,
                occurred_at=parsed.occurred_at,
                ingested_at=ingested_at,
                source_host=parsed.source_host,
                raw_payload=parsed.raw_payload,
                normalized=parsed.normalized,
                ingestion_batch_id=batch_id,
            )
        )
        accepted += 1

    db.flush()

    events_ingested_total.labels(source_type=source_type.value).inc(accepted)
    if errors:
        ingestion_errors_total.labels(source_type=source_type.value).inc(len(errors))

    logger.info(
        "ingestion run completed",
        extra={
            "source_type": source_type.value,
            "batch_id": str(batch_id) if batch_id else None,
            "total": len(raw_records),
            "accepted": accepted,
            "rejected": len(errors),
        },
    )

    return IngestionReport(
        batch_id=batch_id,
        source_type=source_type,
        total=len(raw_records),
        accepted=accepted,
        rejected=len(errors),
        errors=errors,
    )
