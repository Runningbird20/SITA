from datetime import UTC, datetime

from app.mitre.rollup import incident_technique_rollup, techniques_by_tactic
from app.models.alert import Alert
from app.models.analysis_result import AnalysisResult
from app.models.associations import AlertMitreMapping
from app.models.detection import Detection
from app.models.enums import (
    AnalysisTaskType,
    AnalysisValidationStatus,
    DetectionCategory,
    IncidentStatus,
    MitreMappingSource,
    Severity,
)
from app.models.incident import Incident
from app.models.mitre import MITRETechnique

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)


def _make_incident_with_alert(db_session) -> tuple[Incident, Alert]:
    detection = Detection(
        rule_key="test_rule",
        name="Test Rule",
        description="A test rule.",
        category=DetectionCategory.AUTHENTICATION,
        default_severity=Severity.HIGH,
        enabled=True,
    )
    db_session.add(detection)
    db_session.flush()

    incident = Incident(
        title="Test Incident",
        status=IncidentStatus.OPEN,
        severity=Severity.HIGH,
        first_activity_at=NOW,
        last_activity_at=NOW,
        correlation_method={},
    )
    db_session.add(incident)
    db_session.flush()

    alert = Alert(
        detection_id=detection.id,
        incident_id=incident.id,
        severity=Severity.HIGH,
        confidence=0.8,
        rationale="test",
        severity_factors={},
        first_event_at=NOW,
        last_event_at=NOW,
    )
    db_session.add(alert)
    db_session.flush()
    return incident, alert


class TestIncidentTechniqueRollup:
    def test_groups_by_technique_and_tracks_sources(self, db_session):
        incident, alert = _make_incident_with_alert(db_session)
        technique = MITRETechnique(
            technique_id="T1110.001",
            name="Password Guessing",
            tactic="credential-access",
            description="desc",
            dataset_version="test",
        )
        db_session.add(technique)
        db_session.flush()

        db_session.add(
            AlertMitreMapping(
                alert_id=alert.id,
                technique_id=technique.id,
                source=MitreMappingSource.RULE,
            )
        )
        db_session.flush()
        db_session.commit()
        db_session.refresh(incident)

        entries = incident_technique_rollup(incident)

        assert len(entries) == 1
        assert entries[0].technique_id == "T1110.001"
        assert entries[0].sources == {"rule"}
        assert len(entries[0].evidence) == 1
        assert entries[0].evidence[0].confidence is None

    def test_same_technique_from_both_sources_shows_both(self, db_session):
        incident, alert = _make_incident_with_alert(db_session)
        technique = MITRETechnique(
            technique_id="T1078",
            name="Valid Accounts",
            tactic="initial-access",
            description="desc",
            dataset_version="test",
        )
        db_session.add(technique)
        db_session.flush()

        analysis_result = AnalysisResult(
            incident_id=incident.id,
            task_type=AnalysisTaskType.MITRE_SUGGESTION,
            provider="mock",
            model="mock-model",
            prompt_version="v1",
            raw_output="{}",
            parsed_output={},
            validation_status=AnalysisValidationStatus.VALID,
            confidence=0.85,
            latency_ms=1,
        )
        db_session.add(analysis_result)
        db_session.flush()

        db_session.add(
            AlertMitreMapping(
                alert_id=alert.id, technique_id=technique.id, source=MitreMappingSource.RULE
            )
        )
        db_session.add(
            AlertMitreMapping(
                alert_id=alert.id,
                technique_id=technique.id,
                source=MitreMappingSource.LLM,
                analysis_result_id=analysis_result.id,
            )
        )
        db_session.flush()
        db_session.commit()
        db_session.refresh(incident)

        entries = incident_technique_rollup(incident)

        assert len(entries) == 1
        assert entries[0].sources == {"rule", "llm"}
        assert len(entries[0].evidence) == 2
        confidences = {e.confidence for e in entries[0].evidence}
        assert confidences == {None, 0.85}

    def test_no_mappings_yields_empty_rollup(self, db_session):
        incident, _alert = _make_incident_with_alert(db_session)
        db_session.commit()
        db_session.refresh(incident)

        assert incident_technique_rollup(incident) == []


class TestTechniquesByTactic:
    def test_groups_entries_by_tactic(self, db_session):
        incident, alert = _make_incident_with_alert(db_session)
        t1 = MITRETechnique(
            technique_id="T1110.001",
            name="Password Guessing",
            tactic="credential-access",
            description="desc",
            dataset_version="test",
        )
        t2 = MITRETechnique(
            technique_id="T1046",
            name="Network Service Discovery",
            tactic="discovery",
            description="desc",
            dataset_version="test",
        )
        db_session.add_all([t1, t2])
        db_session.flush()
        db_session.add_all(
            [
                AlertMitreMapping(
                    alert_id=alert.id, technique_id=t1.id, source=MitreMappingSource.RULE
                ),
                AlertMitreMapping(
                    alert_id=alert.id, technique_id=t2.id, source=MitreMappingSource.RULE
                ),
            ]
        )
        db_session.flush()
        db_session.commit()
        db_session.refresh(incident)

        grouped = techniques_by_tactic(incident_technique_rollup(incident))

        assert set(grouped.keys()) == {"credential-access", "discovery"}
        assert len(grouped["credential-access"]) == 1
        assert len(grouped["discovery"]) == 1
