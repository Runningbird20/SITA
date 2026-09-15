"""Run the full pipeline on a fixed interval, forever, until interrupted.

Usage:
    uv run python -m app.scheduler.cli [--interval-seconds 300]

See DEF.md § Phase 9, "Post-roadmap addition: scheduled pipeline runs".
"""

import argparse
import sys

from app.scheduler.runner import run_scheduler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=int, default=300)
    args = parser.parse_args(argv)

    run_scheduler(interval_seconds=args.interval_seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
