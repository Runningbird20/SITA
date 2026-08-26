"""Runs the accuracy evaluation against the held-out data/eval/ dataset and
prints a precision/recall/F1 report.

Usage:
    uv run python -m app.evaluation.cli [--json-out path.json]

Deliberately runs against a throwaway in-memory SQLite database, never the
configured DATABASE_URL — an evaluation run must never mix synthetic eval
fixtures (hosts like "eval-sshbf-tp1.internal") into real demo/dev data.
See DEF.md § Phase 12.
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.evaluation.harness import run_evaluation
from app.models import Base


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, default=None, help="Also write the report as JSON")
    args = parser.parse_args(argv)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        report = run_evaluation(db)

    engine.dispose()

    payload = report.as_dict()
    print(json.dumps(payload, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nWrote {args.json_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
