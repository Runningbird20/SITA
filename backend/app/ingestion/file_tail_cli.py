"""Tail a local auth.log-style file and ingest recognized sshd auth
activity as it's appended.

Usage:
    uv run python -m app.ingestion.file_tail_cli /var/log/auth.log [--from-start]

See DEF.md § Phase 2, "Post-roadmap addition: real ingestion (syslog +
file-tail)".
"""

import argparse
import sys
from pathlib import Path

from app.ingestion.file_tail import tail_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--from-start",
        action="store_true",
        help="Ingest the file's existing content too, not just lines appended after startup.",
    )
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"No such file: {args.path}", file=sys.stderr)
        return 1

    tail_file(args.path, from_start=args.from_start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
