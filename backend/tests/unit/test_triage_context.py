from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.models.enums import SourceType
from app.models.incident import Incident
from app.triage.context import build_incident_context, render_context_block

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)


def _make_incident(db_session, make_event) -> Incident:
    for i in range(10):
        make_event(
            SourceType.AUTH,
            NOW + timedelta(seconds=i * 20),
            {
                "event_result": "failure",
                "username": "admin",
                "source_ip": "198.51.100.1",
                "dest_host": "db01.internal",
                "auth_method": "password",
            },
            host="db01.internal",
        )
    db_session.commit()
    run_detection(db_session)
    db_session.commit()
    run_correlation(db_session)
    db_session.commit()
    return db_session.scalars(select(Incident)).one()


class TestBuildIncidentContext:
    def test_includes_alert_and_incident_fields(self, db_session, make_event):
        incident = _make_incident(db_session, make_event)

        ctx = build_incident_context(incident)

        assert ctx.incident_id == incident.id
        assert ctx.title == incident.title
        assert len(ctx.alerts) == 1
        assert ctx.alerts[0].detection_name
        assert ctx.rule_mitre_techniques == []

    def test_deduplicates_iocs_across_alerts(self, db_session, make_event):
        incident = _make_incident(db_session, make_event)
        from app.ioc.pipeline import run_ioc_extraction

        run_ioc_extraction(db_session)
        db_session.commit()
        db_session.refresh(incident)

        ctx = build_incident_context(incident)

        assert len(ctx.ioc_summaries) == len(set(ctx.ioc_summaries))


class TestRenderContextBlock:
    def test_renders_none_yet_for_empty_mitre_mappings(self, db_session, make_event):
        incident = _make_incident(db_session, make_event)
        ctx = build_incident_context(incident)

        block = render_context_block(ctx)

        assert "none yet" in block
        assert incident.title in block
        assert ctx.alerts[0].detection_name in block
