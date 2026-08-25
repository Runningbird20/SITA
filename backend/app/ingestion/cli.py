"""Batch-import a JSON Lines file of simulated security events.

Usage:
    uv run python -m app.ingestion.cli <source_type> <path/to/file.jsonl>

This is the "batch file import" pathway from DEF.md § Phase 2 §4 — every
accepted record in the file is stamped with the same freshly-generated
`ingestion_batch_id`. Also doubles as the loader for the synthetic
datasets under data/synthetic_events/ (see Phase 15's quick-start).
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

from app.db.session import SessionLocal
from app.ingestion.service import ingest_records
from app.models.enums import SourceType
from app.schemas.ingestion import IngestionReport


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def run_import(source_type: SourceType, path: Path) -> IngestionReport:
    records = load_jsonl(path)
    batch_id = uuid.uuid4()

    db = SessionLocal()
    try:
        report = ingest_records(
            db=db, source_type=source_type, raw_records=records, batch_id=batch_id
        )
        db.commit()
    finally:
        db.close()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_type", choices=[s.value for s in SourceType])
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)

    report = run_import(SourceType(args.source_type), args.path)
    print(report.model_dump_json(indent=2))
    return 0 if report.rejected == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
