from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.correlation.base import AlertSignature, CorrelationConfig, IncidentSignature
from app.correlation.scoring import score_alert_against_incident
from app.detection.pipeline import run_detection
from app.mitre.loader import load_techniques
from app.mitre.pipeline import run_mitre_mapping
from app.models.alert import Alert
from app.models.associations import AlertMitreMapping
from app.models.detection import Detection
from app.models.enums import MitreMappingSource, SourceType

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)


def _brute_force_events(make_event, source_ip="198.51.100.1", dest_host="db01.internal"):
    for i in range(10):
        make_event(
            SourceType.AUTH,
            NOW + timedelta(seconds=i * 20),
            {
                "event_result": "failure",
                "username": "admin",
                "source_ip": source_ip,
                "dest_host": dest_host,
                "auth_method": "password",
            },
            host=dest_host,
        )


class TestRunMitreMapping:
    def test_links_detection_to_its_declared_technique(self, db_session, make_event):
        load_techniques(db_session)
        _brute_force_events(make_event)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        report = run_mitre_mapping(db_session)
        db_session.commit()

        detection = db_session.scalars(
            select(Detection).where(Detection.rule_key == "ssh_brute_force")
        ).one()
        assert {t.technique_id for t in detection.mitre_techniques} == {"T1110.001"}
        assert report.detection_technique_links_created >= 1

    def test_creates_rule_sourced_alert_mapping(self, db_session, make_event):
        load_techniques(db_session)
        _brute_force_events(make_event)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        report = run_mitre_mapping(db_session)
        db_session.commit()

        alert = db_session.scalars(select(Alert)).one()
        mappings = db_session.scalars(
            select(AlertMitreMapping).where(AlertMitreMapping.alert_id == alert.id)
        ).all()
        assert len(mappings) == 1
        assert mappings[0].source == MitreMappingSource.RULE
        assert mappings[0].analysis_result_id is None
        assert mappings[0].technique.technique_id == "T1110.001"
        assert report.alert_technique_mappings_created == 1

    def test_no_mappings_created_when_techniques_not_yet_loaded(self, db_session, make_event):
        # No load_techniques() call — the local table is empty.
        _brute_force_events(make_event)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        report = run_mitre_mapping(db_session)
        db_session.commit()

        assert report.detection_technique_links_created == 0
        assert report.alert_technique_mappings_created == 0
        assert db_session.scalars(select(AlertMitreMapping)).all() == []

    def test_rerun_is_idempotent(self, db_session, make_event):
        load_techniques(db_session)
        _brute_force_events(make_event)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        run_mitre_mapping(db_session)
        db_session.commit()

        second_report = run_mitre_mapping(db_session)
        db_session.commit()

        assert second_report.detection_technique_links_created == 0
        assert second_report.alert_technique_mappings_created == 0
        assert len(db_session.scalars(select(AlertMitreMapping)).all()) == 1

    def test_self_heals_once_techniques_are_loaded_late(self, db_session, make_event):
        _brute_force_events(make_event)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        first_report = run_mitre_mapping(db_session)
        db_session.commit()
        assert first_report.alert_technique_mappings_created == 0

        load_techniques(db_session)
        db_session.commit()
        second_report = run_mitre_mapping(db_session)
        db_session.commit()

        assert second_report.alert_technique_mappings_created == 1
        assert len(db_session.scalars(select(AlertMitreMapping)).all()) == 1

    def test_since_scopes_the_alert_pass(self, db_session, make_event):
        load_techniques(db_session)
        _brute_force_events(make_event)
        db_session.commit()
        run_detection(db_session)
        db_session.commit()

        report = run_mitre_mapping(db_session, since=NOW + timedelta(days=1))
        db_session.commit()

        assert report.alerts_processed == 0
        assert report.alert_technique_mappings_created == 0


class TestFeedsCorrelationMitreSignal:
    """Phase 5's IncidentSignature/score_alert_against_incident already read
    alert.mitre_mappings — documented in TODO.md as "real, tested code
    path... but inert in practice until Phase 8 populates technique
    mappings." This confirms that claim: once run_mitre_mapping has run,
    the same unmodified Phase 5 scoring function produces a real, nonzero
    MITRE-agreement contribution from real data.
    """

    def test_shared_technique_produces_nonzero_mitre_score(self, db_session, make_event):
        load_techniques(db_session)
        # Two unrelated ssh_brute_force firings, far apart in time and with
        # no shared IP/host — only the technique (both T1110.001) overlaps.
        _brute_force_events(make_event, source_ip="198.51.100.1", dest_host="db01.internal")
        _brute_force_events(make_event, source_ip="203.0.113.9", dest_host="app02.internal")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        run_mitre_mapping(db_session)
        db_session.commit()

        alerts = db_session.scalars(select(Alert)).all()
        assert len(alerts) == 2

        def _signature(alert: Alert) -> AlertSignature:
            return AlertSignature(
                alert_id=alert.id,
                ioc_ids=set(),
                host_entity_ids=set(),
                technique_ids={m.technique_id for m in alert.mitre_mappings},
                first_event_at=alert.first_event_at,
                last_event_at=alert.last_event_at,
            )

        alert_a, alert_b = alerts
        sig_a = _signature(alert_a)
        assert sig_a.technique_ids, "alert has no technique_ids — mapping did not populate"

        incident_sig = IncidentSignature(incident_id=alert_a.id)
        incident_sig.merge(sig_a)

        breakdown = score_alert_against_incident(
            _signature(alert_b), incident_sig, CorrelationConfig()
        )

        assert breakdown.mitre_score > 0
        assert breakdown.shared_technique_ids == sig_a.technique_ids
