"""Load the vendored local MITRE ATT&CK subset and sync it onto Detections
and Alerts.

Usage:
    uv run python -m app.mitre.cli [--since 2026-01-15T00:00:00Z]

Recommended order: run after `app.detection.cli`/`app.ioc.cli` and before
`app.correlation.cli`, so correlation's MITRE-agreement signal (dormant
since Phase 5, per DEF.md § Phase 8) has real data to score against.
"""

import argparse
import sys
from datetime import datetime

from app.db.session import SessionLocal
from app.mitre.loader import load_techniques
from app.mitre.pipeline import run_mitre_mapping


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="ISO 8601 UTC timestamp; only sync alerts at or after this time",
    )
    args = parser.parse_args(argv)

    since = datetime.fromisoformat(args.since.replace("Z", "+00:00")) if args.since else None

    db = SessionLocal()
    try:
        load_report = load_techniques(db)
        mapping_report = run_mitre_mapping(db, since=since)
        db.commit()
    finally:
        db.close()

    print(load_report.model_dump_json(indent=2))
    print(mapping_report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
