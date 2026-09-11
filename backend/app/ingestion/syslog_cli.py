"""Run the RFC 5424 syslog listener as a standalone process.

Usage:
    uv run python -m app.ingestion.syslog_cli [--host 0.0.0.0] [--port 5514]

Point a real syslog daemon at this host:port (e.g. rsyslog's
`*.* @@this-host:5514;RSYSLOG_SyslogProtocol23Format` for RFC 5424
framing) to ingest real sshd auth activity — see DEF.md § Phase 2,
"Post-roadmap addition: real ingestion (syslog + file-tail)".
"""

import argparse
import sys

from app.ingestion.syslog_listener import run_listener


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5514)
    args = parser.parse_args(argv)

    run_listener(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
