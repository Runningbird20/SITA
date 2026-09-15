"""Run the concurrent write-load stress test and print a report.

Usage:
    uv run python -m app.benchmark.concurrent_load_cli [--concurrency 10]
        [--requests-per-worker 10] [--events-per-request 20]

Runs against a throwaway in-memory database, never the configured
DATABASE_URL. See DEF.md § Phase 12, "Post-roadmap addition:
concurrent-write stress test".
"""

import argparse
import json
import sys

from app.benchmark.concurrent_load import run_concurrent_write_load


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests-per-worker", type=int, default=10)
    parser.add_argument("--events-per-request", type=int, default=20)
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="A real Postgres URL to test against instead of throwaway in-memory SQLite. "
        "Must point at a disposable database — never the configured DATABASE_URL.",
    )
    args = parser.parse_args(argv)

    result = run_concurrent_write_load(
        concurrency=args.concurrency,
        requests_per_worker=args.requests_per_worker,
        events_per_request=args.events_per_request,
        database_url=args.database_url,
    )
    print(json.dumps(result.as_dict(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
