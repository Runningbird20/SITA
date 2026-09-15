"""A minimal RFC 5424 UDP syslog listener that maps recognized sshd
auth-log messages onto AUTH ingestion events — real logs from a real box,
still fully local, no cloud dependency. See DEF.md § Phase 2,
"Post-roadmap addition: real ingestion (syslog + file-tail)".

Deliberately UDP-only (the traditional syslog transport, RFC 5426) and
deliberately sshd-auth-only (see syslog_parser.py) — not a general-purpose
syslog server. Buffers received messages and flushes to the database
every `flush_interval_seconds`, or immediately once `batch_size` is
reached, rather than one INSERT per UDP datagram.

Usage:
    uv run python -m app.ingestion.syslog_cli [--host 0.0.0.0] [--port 5514]
"""

import logging
import socketserver
import time
import uuid

from app.db.session import SessionLocal
from app.ingestion.service import ingest_records
from app.ingestion.syslog_parser import parse_rfc5424_line
from app.models.enums import SourceType

logger = logging.getLogger(__name__)


class _BufferedSyslogServer(socketserver.UDPServer):
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.buffer: list[dict] = []


class _SyslogUDPHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = self.request[0]
        try:
            line = data.decode("utf-8", errors="replace")
        except UnicodeDecodeError:
            return
        event = parse_rfc5424_line(line)
        if event is not None:
            self.server.buffer.append(event)  # type: ignore[attr-defined]


def _flush(server: _BufferedSyslogServer) -> None:
    if not server.buffer:
        return
    batch = server.buffer
    server.buffer = []
    db = SessionLocal()
    try:
        report = ingest_records(db, SourceType.AUTH, batch, batch_id=uuid.uuid4())
        db.commit()
        logger.info(
            "syslog batch ingested",
            extra={"accepted": report.accepted, "rejected": report.rejected},
        )
    finally:
        db.close()


def run_listener(
    host: str = "0.0.0.0",
    port: int = 5514,
    batch_size: int = 50,
    flush_interval_seconds: float = 5.0,
) -> None:
    server = _BufferedSyslogServer((host, port), _SyslogUDPHandler)
    server.timeout = flush_interval_seconds
    last_flush = time.monotonic()
    logger.info("syslog listener started", extra={"host": host, "port": port})

    try:
        while True:
            server.handle_request()  # blocks for one datagram, up to server.timeout
            now = time.monotonic()
            if server.buffer and (
                len(server.buffer) >= batch_size or now - last_flush >= flush_interval_seconds
            ):
                _flush(server)
                last_flush = now
    except KeyboardInterrupt:
        pass
    finally:
        _flush(server)
        server.server_close()
