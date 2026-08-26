"""Runs the performance benchmark and prints a report.

Usage:
    uv run python -m app.benchmark.cli [--events-per-source 500] [--api-requests 100] [--json-out path.json]

Runs against a throwaway in-memory database, never the configured
DATABASE_URL. See DEF.md § Phase 12.
"""

import argparse
import json
import sys
from pathlib import Path

from app.benchmark.harness import run_benchmark


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events-per-source", type=int, default=500)
    parser.add_argument("--api-requests", type=int, default=100)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_benchmark(events_per_source=args.events_per_source, api_requests=args.api_requests)

    payload = report.as_dict()
    print(json.dumps(payload, indent=2))
    if args.json_out:
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"\nWrote {args.json_out}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
