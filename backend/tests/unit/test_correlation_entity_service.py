from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.correlation.entity_service import link_alert, link_event, upsert_host_entity
from app.models.alert import Alert
from app.models.entity import Entity
from app.models.enums import AlertStatus, EntityRole, SourceType

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


class TestUpsertHostEntity:
    def test_creates_new_entity_on_first_sighting(self, db_session):
        entity, created = upsert_host_entity(db_session, "web01.internal", NOW)
        assert created is True
        assert entity.first_seen == NOW
        assert entity.last_seen == NOW

    def test_second_sighting_updates_not_duplicates(self, db_session):
        upsert_host_entity(db_session, "web01.internal", NOW)
        entity, created = upsert_host_entity(db_session, "web01.internal", NOW + timedelta(hours=1))
        assert created is False
        assert len(db_session.scalars(select(Entity)).all()) == 1


class TestLinkEvent:
    def test_links_event_with_role_and_reports_new_link(self, db_session, make_event):
        event = make_event(SourceType.AUTH, NOW, {"dest_host": "web01.internal"})
        entity, _ = upsert_host_entity(db_session, "web01.internal", NOW)
        created = link_event(db_session, entity, event, EntityRole.SOURCE)
        assert created is True

    def test_relinking_same_role_is_a_noop(self, db_session, make_event):
        event = make_event(SourceType.AUTH, NOW, {"dest_host": "web01.internal"})
        entity, _ = upsert_host_entity(db_session, "web01.internal", NOW)
        link_event(db_session, entity, event, EntityRole.SOURCE)
        db_session.flush()
        created_again = link_event(db_session, entity, event, EntityRole.SOURCE)
        assert created_again is False

    def test_different_roles_both_link(self, db_session, make_event):
        event = make_event(SourceType.NETWORK, NOW, {"src_ip": "10.0.0.5", "dst_ip": "10.0.0.7"})
        entity, _ = upsert_host_entity(db_session, "10.0.0.5", NOW)
        link_event(db_session, entity, event, EntityRole.SOURCE)
        db_session.flush()
        created = link_event(db_session, entity, event, EntityRole.TARGET)
        assert created is True


class TestLinkAlert:
    def test_links_alert_and_reports_new_link(self, db_session, make_event):
        from app.models.detection import Detection

        detection = Detection(
            rule_key="test_rule",
            name="Test Rule",
            description="...",
            category="network",
            default_severity="low",
        )
        alert = Alert(
            detection=detection,
            severity="low",
            confidence=0.5,
            status=AlertStatus.NEW,
            rationale="test",
            severity_factors={},
            first_event_at=NOW,
            last_event_at=NOW,
        )
        db_session.add_all([detection, alert])
        db_session.flush()

        entity, _ = upsert_host_entity(db_session, "web01.internal", NOW)
        created = link_alert(db_session, entity, alert, EntityRole.SOURCE)
        assert created is True
        assert entity in [link.entity for link in alert.entity_links]
