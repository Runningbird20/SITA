"""Run the detection engine against currently-persisted SecurityEvents.

Usage:
    uv run python -m app.detection.cli [--since 2026-01-15T00:00:00Z]
"""

import argparse
import sys
from datetime import datetime

from app.db.session import SessionLocal
from app.detection.pipeline import run_detection


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
        report = run_detection(db, since=since)
        db.commit()
    finally:
        db.close()

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
