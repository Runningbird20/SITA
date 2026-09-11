"""Server-Sent Events stream logic for "a new incident was just created"
— resolves WHATNEXT.md's "Live updates" item. See DEF.md § Phase 9,
"Post-roadmap addition: live incident updates (SSE)".

Deliberately DB-polling, not a real push mechanism (in-process pub/sub or
Redis pub/sub) — a connected client's own request handler polls
Incident.created_at every poll_interval_seconds and streams anything new.
This is correct out of the box under docker-compose.prod.yml's
multi-worker backend with zero extra plumbing (every worker just queries
the same database — no cross-worker broadcast to get right), at the cost
of up-to-poll_interval_seconds latency rather than true instant push. A
real push mechanism was considered and not built: it would need either
in-process pub/sub (wrong across multiple workers) or Redis pub/sub
(correct, but makes Redis a hard requirement for this feature, the same
tradeoff already declined for the task queue in "Post-roadmap addition:
background pipeline jobs") for a latency improvement a demo-scale project
doesn't need.

The actual route lives on app/api/events.py's router (not a separate
router mounted at the same /events prefix) and is registered *before*
GET /{event_id} — a static "/stream" segment registered after a
path-param route on the same prefix would be shadowed by it (FastAPI
matches "/events/stream" against "/events/{event_id}" first, fails UUID
coercion on "stream", and returns 422 without ever trying the later
route). Caught by reasoning through FastAPI's route-matching order before
writing the endpoint, not by hitting it live.
"""

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.incident import Incident

POLL_INTERVAL_SECONDS = 2.0
_KEEPALIVE_EVERY_N_POLLS = 15  # ~30s at the default poll interval


def new_incidents_since(db: Session, since: datetime) -> list[Incident]:
    stmt = select(Incident).where(Incident.created_at > since).order_by(Incident.created_at)
    return list(db.scalars(stmt).all())


def to_sse_event(incident: Incident) -> str:
    payload = {
        "incident_id": str(incident.id),
        "title": incident.title,
        "severity": str(incident.severity),
        "created_at": incident.created_at.isoformat(),
    }
    return f"event: incident_created\ndata: {json.dumps(payload)}\n\n"


async def stream_new_incidents(request: Request, since: datetime) -> AsyncGenerator[str, None]:
    poll_count = 0
    try:
        while True:
            if await request.is_disconnected():
                break

            db = SessionLocal()
            try:
                new_incidents = new_incidents_since(db, since)
            finally:
                db.close()

            for incident in new_incidents:
                since = incident.created_at
                yield to_sse_event(incident)

            poll_count += 1
            if not new_incidents and poll_count % _KEEPALIVE_EVERY_N_POLLS == 0:
                yield ": keep-alive\n\n"

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        pass


def default_start_timestamp() -> datetime:
    return datetime.now(UTC)
