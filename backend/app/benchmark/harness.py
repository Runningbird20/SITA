"""Performance benchmarks: ingestion throughput, per-stage pipeline
throughput, and API latency percentiles. See DEF.md § Phase 12.

This project's pipelines are batch jobs, not a per-event streaming
service — "detection latency (event ingested -> alert produced)" is
reported as a batch wall-clock time and a derived events/sec throughput,
not a per-event streaming latency, since the latter would misrepresent
the actual architecture.

Runs against an isolated in-memory database, same reasoning as the
evaluation harness: never load throwaway load-test data into the real
configured DATABASE_URL.
"""

import time
from dataclasses import dataclass, field

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.benchmark.generate_load import generate_all
from app.correlation.pipeline import run_correlation
from app.db.session import get_db
from app.detection.pipeline import run_detection
from app.ingestion.service import ingest_records
from app.ioc.pipeline import run_ioc_extraction
from app.llm.mock_provider import MockProvider
from app.llm.types import LLMConfig, RawCompletion
from app.main import app
from app.mitre.loader import load_techniques
from app.mitre.pipeline import run_mitre_mapping
from app.models import Base
from app.models.enums import SourceType
from app.models.incident import Incident
from app.triage.pipeline import run_triage


@dataclass
class StageResult:
    label: str
    seconds: float
    unit_count: int

    @property
    def units_per_second(self) -> float:
        return self.unit_count / self.seconds if self.seconds > 0 else float("inf")

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "seconds": round(self.seconds, 4),
            "unit_count": self.unit_count,
            "units_per_second": round(self.units_per_second, 2),
        }


@dataclass
class LatencyPercentiles:
    label: str
    samples_ms: list[float]

    def _percentile(self, p: float) -> float:
        if not self.samples_ms:
            return 0.0
        ordered = sorted(self.samples_ms)
        idx = min(len(ordered) - 1, int(len(ordered) * p))
        return ordered[idx]

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "n": len(self.samples_ms),
            "p50_ms": round(self._percentile(0.50), 2),
            "p95_ms": round(self._percentile(0.95), 2),
            "p99_ms": round(self._percentile(0.99), 2),
        }


@dataclass
class BenchmarkReport:
    stages: list[StageResult] = field(default_factory=list)
    api_latencies: list[LatencyPercentiles] = field(default_factory=list)
    triage_mock_latency_ms: float | None = None

    def as_dict(self) -> dict:
        return {
            "pipeline_stages": [s.as_dict() for s in self.stages],
            "api_latency": [a.as_dict() for a in self.api_latencies],
            "triage_orchestration_overhead_ms_per_call": self.triage_mock_latency_ms,
        }


def _time_it(fn) -> float:
    start = time.perf_counter()
    fn()
    return time.perf_counter() - start


def run_benchmark(events_per_source: int = 500, api_requests: int = 100) -> BenchmarkReport:
    report = BenchmarkReport()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    events_by_source = generate_all(events_per_source)
    total_events = sum(len(v) for v in events_by_source.values())

    with Session(engine) as db:
        elapsed = _time_it(
            lambda: [
                ingest_records(
                    db=db, source_type=SourceType(source), raw_records=records, batch_id=None
                )
                for source, records in events_by_source.items()
            ]
        )
        db.commit()
        report.stages.append(StageResult("ingestion", elapsed, total_events))

        detection_report = {}
        elapsed = _time_it(lambda: detection_report.update({"r": run_detection(db)}))
        db.commit()
        report.stages.append(StageResult("detection", elapsed, total_events))
        alerts_created = detection_report["r"].alerts_created

        elapsed = _time_it(lambda: run_ioc_extraction(db))
        db.commit()
        report.stages.append(StageResult("ioc_extraction", elapsed, total_events))

        load_techniques(db)
        db.commit()
        elapsed = _time_it(lambda: run_mitre_mapping(db))
        db.commit()
        report.stages.append(StageResult("mitre_mapping", elapsed, max(alerts_created, 1)))

        elapsed = _time_it(lambda: run_correlation(db))
        db.commit()
        report.stages.append(StageResult("correlation", elapsed, max(alerts_created, 1)))

        incident_count = len(db.scalars(select(Incident)).all())
        mock_provider = MockProvider(responses=RawCompletion(text="{}"))
        fast_config = LLMConfig(model="bench", max_retries=0, retry_backoff_seconds=0)
        elapsed = _time_it(
            lambda: run_triage(db, provider=mock_provider, config=fast_config, force=True)
        )
        db.commit()
        report.stages.append(
            StageResult("triage_orchestration_mock", elapsed, max(incident_count, 1))
        )
        # 6 tasks per incident — per-call overhead, not per-incident.
        report.triage_mock_latency_ms = round((elapsed / max(incident_count * 6, 1)) * 1000, 4)

    def _override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as client:
            for path, label in [
                ("/api/v1/incidents?limit=25", "GET /incidents (list)"),
                ("/api/v1/alerts?limit=25", "GET /alerts (list)"),
                ("/api/v1/iocs?search=10.9&limit=25", "GET /iocs (search)"),
            ]:
                samples = []
                for _ in range(api_requests):
                    start = time.perf_counter()
                    client.get(path)
                    samples.append((time.perf_counter() - start) * 1000)
                report.api_latencies.append(LatencyPercentiles(label, samples))
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

    return report
