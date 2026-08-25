"""Run AI-powered triage against persisted Incidents.

Usage:
    uv run python -m app.triage.cli [--incident-id UUID] [--since 2026-01-15T00:00:00Z] [--force]

Recommended order: run after `app.correlation.cli`, so incidents exist to
triage. Uses whichever LLMProvider `Settings.llm_provider` configures
(mock by default — no network calls).
"""

import argparse
import sys
import uuid
from datetime import datetime

from app.db.session import SessionLocal
from app.triage.pipeline import run_triage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--incident-id",
        type=str,
        default=None,
        help="UUID of a single incident to triage; omit to triage every incident",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="ISO 8601 UTC timestamp; only consider incidents active at or after this time",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate every task even if a result already exists for its prompt_version",
    )
    args = parser.parse_args(argv)

    incident_id = uuid.UUID(args.incident_id) if args.incident_id else None
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00")) if args.since else None

    db = SessionLocal()
    try:
        report = run_triage(db, incident_id=incident_id, since=since, force=args.force)
        db.commit()
    finally:
        db.close()

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
