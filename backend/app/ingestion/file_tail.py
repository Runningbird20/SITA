"""Tails a local auth.log-style file for newly appended lines, parsing
each via the same sshd auth-log parser the syslog listener uses —
"point it at your own machine's logs" with no listener or network setup
at all. See DEF.md § Phase 2, "Post-roadmap addition: real ingestion
(syslog + file-tail)".

Classic polling tail -f, not inotify/watchdog — no new dependency, and
polling at poll_interval_seconds is more than fast enough for a log file
that isn't itself a high-throughput stream. Starts at the end of the file
(only genuinely new lines going forward), not the beginning — a file
already containing a year of history shouldn't get bulk-ingested by
accident just because the tailer started.

The embedded per-line timestamp is intentionally not parsed (see
app.ingestion.syslog_parser's docstring) — each event's `timestamp` is
this process's own observation time instead, which is accurate enough for
a live tail (new lines are read close to when they're appended) without
the complexity of inferring a year from a year-less BSD timestamp.

Usage:
    uv run python -m app.ingestion.file_tail_cli /var/log/auth.log
"""

import logging
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.db.session import SessionLocal
from app.ingestion.service import ingest_records
from app.ingestion.syslog_parser import extract_plain_log_fields, parse_ssh_auth_message
from app.models.enums import SourceType

logger = logging.getLogger(__name__)


def _parse_line(line: str) -> dict | None:
    fields = extract_plain_log_fields(line)
    if fields is None or fields["appname"].lower() not in {"sshd", "ssh"}:
        return None
    timestamp = datetime.now(UTC).isoformat()
    return parse_ssh_auth_message(fields["msg"], fields["hostname"], timestamp)


def _flush(db_factory, buffer: list[dict]) -> list[dict]:
    if not buffer:
        return buffer
    db = db_factory()
    try:
        report = ingest_records(db, SourceType.AUTH, buffer, batch_id=uuid.uuid4())
        db.commit()
        logger.info(
            "file-tail batch ingested",
            extra={"accepted": report.accepted, "rejected": report.rejected},
        )
    finally:
        db.close()
    return []


def tail_file(
    path: Path,
    poll_interval_seconds: float = 1.0,
    batch_size: int = 50,
    flush_interval_seconds: float = 5.0,
    from_start: bool = False,
    db_factory=SessionLocal,
    max_iterations: int | None = None,
) -> None:
    """`max_iterations` and `db_factory` exist for testability (a bounded
    run and an injectable session factory) — production usage
    (file_tail_cli.py) never passes either, so the loop below runs
    forever until interrupted.
    """
    buffer: list[dict] = []
    last_flush = time.monotonic()
    iterations = 0

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        if not from_start:
            handle.seek(0, 2)  # end of file — only lines appended after this point

        try:
            while max_iterations is None or iterations < max_iterations:
                iterations += 1
                line = handle.readline()
                if not line:
                    now = time.monotonic()
                    if buffer and now - last_flush >= flush_interval_seconds:
                        buffer = _flush(db_factory, buffer)
                        last_flush = now
                    time.sleep(poll_interval_seconds)
                    continue

                event = _parse_line(line)
                if event is not None:
                    buffer.append(event)
                if len(buffer) >= batch_size:
                    buffer = _flush(db_factory, buffer)
                    last_flush = time.monotonic()
        except KeyboardInterrupt:
            pass
        finally:
            _flush(db_factory, buffer)
