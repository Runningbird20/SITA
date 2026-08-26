from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_db
from app.main import app
from app.models import Base
from app.models.alert import Alert
from app.models.analysis_result import AnalysisResult
from app.models.associations import AlertEntity, AlertMitreMapping
from app.models.detection import Detection
from app.models.entity import Entity
from app.models.enums import (
    AlertStatus,
    AnalysisTaskType,
    AnalysisValidationStatus,
    DetectionCategory,
    EntityRole,
    EntityType,
    ExtractionSource,
    IncidentStatus,
    IOCType,
    MitreMappingSource,
    RecommendationPriority,
    RecommendationSource,
    RecommendationStatus,
    Severity,
    ValidationStatus,
)
from app.models.incident import Incident
from app.models.ioc import IOC
from app.models.mitre import MITRETechnique
from app.models.recommendation import Recommendation

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)


@pytest.fixture
def client():
    """A TestClient wired to a fresh in-memory SQLite DB per test, shared
    by every API integration test. StaticPool: without it, each new
    connection to ":memory:" gets its own fresh (tableless) database — the
    request thread would never see the tables created below.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client, TestingSessionLocal
    app.dependency_overrides.clear()
    engine.dispose()


def seed_full_incident(session_factory: sessionmaker[Session]) -> dict:
    """Builds one incident with a real alert/detection/IOC/MITRE
    mapping/AI analysis/recommendation, via direct ORM construction
    (bypassing the pipelines for speed and precise control) — shared
    across the Phase 9 API test suites so each doesn't have to re-derive
    a realistic, fully-linked object graph. Returns a dict of ids.
    """
    with session_factory() as db:
        detection = Detection(
            rule_key="ssh_brute_force",
            name="SSH Brute Force",
            description="Repeated auth failures.",
            category=DetectionCategory.AUTHENTICATION,
            default_severity=Severity.HIGH,
            enabled=True,
            config={"failure_threshold": 10},
        )
        db.add(detection)
        db.flush()

        technique = MITRETechnique(
            technique_id="T1110.001",
            name="Password Guessing",
            tactic="credential-access",
            description="desc",
            dataset_version="test",
        )
        db.add(technique)
        db.flush()
        detection.mitre_techniques.append(technique)

        incident = Incident(
            title="SSH Brute Force",
            status=IncidentStatus.OPEN,
            severity=Severity.HIGH,
            first_activity_at=NOW,
            last_activity_at=NOW,
            correlation_method={},
        )
        db.add(incident)
        db.flush()

        alert = Alert(
            detection_id=detection.id,
            incident_id=incident.id,
            severity=Severity.HIGH,
            confidence=0.85,
            status=AlertStatus.NEW,
            rationale="10 failed logins from 198.51.100.1",
            severity_factors={"score": 0.8},
            first_event_at=NOW,
            last_event_at=NOW,
        )
        db.add(alert)
        db.flush()

        ioc = IOC(
            ioc_type=IOCType.IPV4,
            value="198.51.100.1",
            extraction_source=ExtractionSource.REGEX,
            validation_status=ValidationStatus.VALID,
            confidence=0.9,
            first_seen=NOW,
            last_seen=NOW,
        )
        db.add(ioc)
        db.flush()
        alert.iocs.append(ioc)

        entity = Entity(
            entity_type=EntityType.HOST,
            identifier="db01.internal",
            first_seen=NOW,
            last_seen=NOW,
        )
        db.add(entity)
        db.flush()
        db.add(AlertEntity(alert_id=alert.id, entity_id=entity.id, role=EntityRole.TARGET))

        db.add(
            AlertMitreMapping(
                alert_id=alert.id, technique_id=technique.id, source=MitreMappingSource.RULE
            )
        )

        analysis_result = AnalysisResult(
            incident_id=incident.id,
            task_type=AnalysisTaskType.INCIDENT_SUMMARY,
            provider="mock",
            model="mock-model",
            prompt_version="v1",
            raw_output="{}",
            parsed_output={"summary": "Brute force attempt."},
            validation_status=AnalysisValidationStatus.VALID,
            confidence=0.9,
            latency_ms=1,
        )
        db.add(analysis_result)
        db.flush()

        recommendation = Recommendation(
            incident_id=incident.id,
            source=RecommendationSource.LLM,
            analysis_result_id=analysis_result.id,
            text="Block the source IP.",
            priority=RecommendationPriority.HIGH,
            status=RecommendationStatus.OPEN,
        )
        db.add(recommendation)
        db.commit()

        return {
            "detection_id": str(detection.id),
            "technique_id": str(technique.id),
            "incident_id": str(incident.id),
            "alert_id": str(alert.id),
            "ioc_id": str(ioc.id),
            "entity_id": str(entity.id),
            "analysis_result_id": str(analysis_result.id),
            "recommendation_id": str(recommendation.id),
        }
