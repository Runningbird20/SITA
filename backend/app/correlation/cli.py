"""Run incident correlation against currently-persisted Alerts.

Usage:
    uv run python -m app.correlation.cli [--since 2026-01-15T00:00:00Z]

Recommended order: run after `app.detection.cli` and `app.ioc.cli`, so the
IOC and host signals are fully populated before scoring runs.
"""

import argparse
import sys
from datetime import datetime

from app.correlation.pipeline import run_correlation
from app.db.session import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="ISO 8601 UTC timestamp; only consider alerts at or after this time",
    )
    args = parser.parse_args(argv)

    since = datetime.fromisoformat(args.since.replace("Z", "+00:00")) if args.since else None

    db = SessionLocal()
    try:
        report = run_correlation(db, since=since)
        db.commit()
    finally:
        db.close()

    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
