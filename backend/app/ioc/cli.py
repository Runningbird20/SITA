"""Run IOC extraction against currently-persisted SecurityEvents.

Usage:
    uv run python -m app.ioc.cli [--since 2026-01-15T00:00:00Z]

Recommended order: run after `app.detection.cli`, so the alert_ioc rollup
(pass 2) has alerts to roll up into. Safe to re-run either way — see
DEF.md § Phase 4.
"""

import argparse
import sys
from datetime import datetime

from app.db.session import SessionLocal
from app.ioc.pipeline import run_ioc_extraction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="ISO 8601 UTC timestamp; only consider events at or after this time",
    )
    args = parser.parse_args(argv)

    since = datetime.fromisoformat(args.since.replace("Z", "+00:00")) if args.since else None

    db = SessionLocal()
    try:
        report = run_ioc_extraction(db, since=since)
        db.commit()
    finally:
        db.close()

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
