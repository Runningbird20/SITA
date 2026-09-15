"""Concurrent write-load stress test — resolves WHATNEXT.md's "no load/
stress testing... under concurrent write load" gap. See DEF.md § Phase 12,
"Post-roadmap addition: concurrent-write stress test".

Fires `concurrency` threads, each posting its own batches of events to
`POST /api/v1/events/{source_type}` concurrently against one shared
in-memory SQLite database (StaticPool) through a real ASGI TestClient —
the same transport integration tests already use, not a hand-rolled
timing loop. SQLite's own single-writer lock is expected to serialize
these writes at the database layer; this test measures and reports that
honestly rather than treating it as a bug — it's a genuine, real property
of the SQLite dev path this project ships, not exercised before this
addition. A real networked Postgres instance (the docker-compose default)
would behave differently under the same load and isn't what this
in-process harness measures.
"""

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.benchmark.generate_load import generate_auth_events
from app.db.session import get_db
from app.main import app
from app.models import Base

_RNG_SEED = 20260301


@dataclass
class ConcurrentLoadResult:
    concurrency: int
    total_requests: int
    total_events: int
    wall_clock_seconds: float
    successful_requests: int
    failed_requests: int
    events_per_second: float
    database: str

    def as_dict(self) -> dict:
        return {
            "database": self.database,
            "concurrency": self.concurrency,
            "total_requests": self.total_requests,
            "total_events": self.total_events,
            "wall_clock_seconds": round(self.wall_clock_seconds, 4),
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "events_per_second": round(self.events_per_second, 2),
        }


def run_concurrent_write_load(
    concurrency: int = 10,
    requests_per_worker: int = 10,
    events_per_request: int = 20,
    database_url: str | None = None,
) -> ConcurrentLoadResult:
    """`database_url`: None (default) uses a throwaway in-memory SQLite
    database via StaticPool — the same single shared connection every
    dev/demo SQLite deployment uses. Pass a real Postgres URL (e.g.
    docker-compose's own `postgres` service) to measure the same
    concurrent load against a real connection-pooled, MVCC database
    instead — this project's own recommended path for anything beyond
    solo local dev, and the direct comparison this stress test exists to
    make. Never the configured DATABASE_URL either way.
    """
    is_sqlite = database_url is None
    if is_sqlite:
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(database_url, pool_size=concurrency, max_overflow=concurrency)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)

    rng = random.Random(_RNG_SEED)
    batches = [
        generate_auth_events(events_per_request, rng)
        for _ in range(concurrency * requests_per_worker)
    ]

    def _post_batch(batch: list[dict]) -> bool:
        # A hard exception here (not just a non-201 response) is itself
        # part of what this test measures under real thread concurrency
        # against a shared SQLite connection — caught and counted as a
        # failure, not allowed to crash the whole harness run, so one
        # worker's contention doesn't hide every other worker's result.
        try:
            response = client.post("/api/v1/events/auth", json=batch)
            return response.status_code == 201
        except Exception:
            return False

    successful = 0
    failed = 0
    start = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(_post_batch, batch) for batch in batches]
            for future in as_completed(futures):
                if future.result():
                    successful += 1
                else:
                    failed += 1
        elapsed = time.perf_counter() - start
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    total_events = successful * events_per_request
    return ConcurrentLoadResult(
        database="sqlite" if is_sqlite else "postgres",
        concurrency=concurrency,
        total_requests=len(batches),
        total_events=total_events,
        wall_clock_seconds=elapsed,
        successful_requests=successful,
        failed_requests=failed,
        events_per_second=total_events / elapsed if elapsed > 0 else float("inf"),
    )
