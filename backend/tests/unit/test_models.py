import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    IOC,
    Alert,
    AlertEntity,
    AlertMitreMapping,
    AnalysisResult,
    Detection,
    Entity,
    EventEntity,
    Incident,
    MITRETechnique,
    Recommendation,
    SecurityEvent,
)
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
    SourceType,
    ValidationStatus,
)

NOW = datetime.now(UTC)


def _make_detection() -> Detection:
    return Detection(
        rule_key="ssh_brute_force",
        name="SSH Brute Force",
        description="Repeated auth failures from one source against one target.",
        category=DetectionCategory.AUTHENTICATION,
        default_severity=Severity.HIGH,
    )


def _make_event() -> SecurityEvent:
    return SecurityEvent(
        source_type=SourceType.AUTH,
        occurred_at=NOW,
        ingested_at=NOW,
        raw_payload={"raw": "line"},
        normalized={"username": "root", "source_ip": "10.0.0.5"},
    )


def _make_alert(detection: Detection) -> Alert:
    return Alert(
        detection=detection,
        severity=Severity.HIGH,
        confidence=0.9,
        status=AlertStatus.NEW,
        rationale="14 failed logins from 10.0.0.5 in 5 minutes.",
        severity_factors={"rule_weight": 0.7, "volume": 0.2},
        first_event_at=NOW,
        last_event_at=NOW,
    )


class TestFullGraphPersists:
    def test_full_entity_graph_round_trips(self, db_session):
        detection = _make_detection()
        technique = MITRETechnique(
            technique_id="T1110.001",
            name="Password Guessing",
            tactic="credential-access",
            description="Adversaries may guess passwords.",
            dataset_version="2025-01",
        )
        detection.mitre_techniques.append(technique)

        entity = Entity(
            entity_type=EntityType.IP,
            identifier="10.0.0.5",
            first_seen=NOW,
            last_seen=NOW,
        )
        event = _make_event()
        db_session.add_all([detection, technique, entity, event])
        db_session.flush()

        db_session.add(EventEntity(event=event, entity=entity, role=EntityRole.SOURCE))

        alert = _make_alert(detection)
        alert.events.append(event)
        db_session.add(alert)
        db_session.flush()

        db_session.add(AlertEntity(alert=alert, entity=entity, role=EntityRole.SOURCE))
        db_session.add(
            AlertMitreMapping(alert=alert, technique=technique, source=MitreMappingSource.RULE)
        )

        ioc = IOC(
            ioc_type=IOCType.IPV4,
            value="10.0.0.5",
            extraction_source=ExtractionSource.REGEX,
            validation_status=ValidationStatus.VALID,
            confidence=1.0,
            first_seen=NOW,
            last_seen=NOW,
        )
        ioc.events.append(event)
        ioc.alerts.append(alert)
        db_session.add(ioc)

        incident = Incident(
            title="SSH brute force -> web01",
            status=IncidentStatus.OPEN,
            severity=Severity.HIGH,
            first_activity_at=NOW,
            last_activity_at=NOW,
            correlation_method={"signals": ["shared_ip"]},
        )
        alert.incident = incident
        db_session.add(incident)
        db_session.flush()

        analysis = AnalysisResult(
            incident=incident,
            task_type=AnalysisTaskType.INCIDENT_SUMMARY,
            provider="mock",
            model="mock-model",
            prompt_version="v1",
            raw_output='{"summary": "..."}',
            parsed_output={"summary": "..."},
            validation_status=AnalysisValidationStatus.VALID,
            latency_ms=42,
        )
        db_session.add(analysis)
        db_session.flush()

        recommendation = Recommendation(
            incident=incident,
            source=RecommendationSource.RULE_BASED,
            text="Block source IP 10.0.0.5",
            priority=RecommendationPriority.HIGH,
            status=RecommendationStatus.OPEN,
        )
        db_session.add(recommendation)
        db_session.commit()

        persisted = db_session.get(Incident, incident.id)
        assert len(persisted.alerts) == 1
        assert persisted.alerts[0].detection.rule_key == "ssh_brute_force"
        assert persisted.alerts[0].mitre_mappings[0].technique.technique_id == "T1110.001"
        assert persisted.alerts[0].entity_links[0].entity.identifier == "10.0.0.5"
        assert len(persisted.analysis_results) == 1
        assert len(persisted.recommendations) == 1


class TestUniqueConstraints:
    def test_entity_type_and_identifier_must_be_unique(self, db_session):
        db_session.add(
            Entity(entity_type=EntityType.USER, identifier="alice", first_seen=NOW, last_seen=NOW)
        )
        db_session.commit()

        db_session.add(
            Entity(entity_type=EntityType.USER, identifier="alice", first_seen=NOW, last_seen=NOW)
        )
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_ioc_type_and_value_must_be_unique(self, db_session):
        kwargs = {
            "ioc_type": IOCType.DOMAIN,
            "value": "evil.example",
            "extraction_source": ExtractionSource.REGEX,
            "validation_status": ValidationStatus.VALID,
            "confidence": 1.0,
            "first_seen": NOW,
            "last_seen": NOW,
        }
        db_session.add(IOC(**kwargs))
        db_session.commit()

        db_session.add(IOC(**kwargs))
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_detection_rule_key_must_be_unique(self, db_session):
        db_session.add(_make_detection())
        db_session.commit()

        db_session.add(_make_detection())
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestRequiredFields:
    def test_detection_without_rule_key_fails(self, db_session):
        detection = Detection(
            rule_key=None,
            name="Missing rule key",
            description="...",
            category=DetectionCategory.NETWORK,
            default_severity=Severity.LOW,
        )
        db_session.add(detection)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestForeignKeyIntegrity:
    def test_alert_requires_existing_detection(self, db_session):
        alert = Alert(
            detection_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            severity=Severity.LOW,
            confidence=0.5,
            status=AlertStatus.NEW,
            rationale="orphaned alert",
            severity_factors={},
            first_event_at=NOW,
            last_event_at=NOW,
        )
        db_session.add(alert)
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestAnalysisResultScopeConstraint:
    def test_rejects_both_incident_and_alert_set(self, db_session):
        detection = _make_detection()
        alert = _make_alert(detection)
        incident = Incident(
            title="test",
            status=IncidentStatus.OPEN,
            severity=Severity.LOW,
            first_activity_at=NOW,
            last_activity_at=NOW,
            correlation_method={},
        )
        db_session.add_all([detection, alert, incident])
        db_session.flush()

        db_session.add(
            AnalysisResult(
                incident=incident,
                alert=alert,
                task_type=AnalysisTaskType.INCIDENT_SUMMARY,
                provider="mock",
                model="mock-model",
                prompt_version="v1",
                raw_output="{}",
                validation_status=AnalysisValidationStatus.VALID,
                latency_ms=1,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_rejects_neither_incident_nor_alert_set(self, db_session):
        db_session.add(
            AnalysisResult(
                task_type=AnalysisTaskType.INCIDENT_SUMMARY,
                provider="mock",
                model="mock-model",
                prompt_version="v1",
                raw_output="{}",
                validation_status=AnalysisValidationStatus.VALID,
                latency_ms=1,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.commit()


class TestRecommendationProvenanceConstraint:
    def test_llm_source_requires_analysis_result(self, db_session):
        incident = Incident(
            title="test",
            status=IncidentStatus.OPEN,
            severity=Severity.LOW,
            first_activity_at=NOW,
            last_activity_at=NOW,
            correlation_method={},
        )
        db_session.add(incident)
        db_session.flush()

        db_session.add(
            Recommendation(
                incident=incident,
                source=RecommendationSource.LLM,
                analysis_result_id=None,
                text="unattributed AI recommendation",
                priority=RecommendationPriority.LOW,
                status=RecommendationStatus.OPEN,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_rule_based_source_rejects_analysis_result(self, db_session):
        incident = Incident(
            title="test",
            status=IncidentStatus.OPEN,
            severity=Severity.LOW,
            first_activity_at=NOW,
            last_activity_at=NOW,
            correlation_method={},
        )
        alert = _make_alert(_make_detection())
        analysis = AnalysisResult(
            incident=incident,
            task_type=AnalysisTaskType.INCIDENT_SUMMARY,
            provider="mock",
            model="mock-model",
            prompt_version="v1",
            raw_output="{}",
            validation_status=AnalysisValidationStatus.VALID,
            latency_ms=1,
        )
        db_session.add_all([incident, alert, analysis])
        db_session.flush()

        db_session.add(
            Recommendation(
                incident=incident,
                source=RecommendationSource.RULE_BASED,
                analysis_result_id=analysis.id,
                text="should not be allowed",
                priority=RecommendationPriority.LOW,
                status=RecommendationStatus.OPEN,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.commit()
