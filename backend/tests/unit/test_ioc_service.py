from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.ioc.base import ExtractedIOC
from app.ioc.service import link_event, upsert_ioc
from app.models.enums import ExtractionSource, IOCType, SourceType, ValidationStatus
from app.models.ioc import IOC

NOW = datetime(2026, 1, 17, 12, 0, 0, tzinfo=UTC)


def _same_instant(a: datetime, b: datetime) -> bool:
    """SQLite doesn't preserve tzinfo through a flush/refresh round-trip —
    a naive value read back is UTC by this project's convention.
    """
    aware_a = a if a.tzinfo is not None else a.replace(tzinfo=UTC)
    aware_b = b if b.tzinfo is not None else b.replace(tzinfo=UTC)
    return aware_a == aware_b


def _candidate(value="185.220.101.5", confidence=0.7):
    return ExtractedIOC(
        ioc_type=IOCType.IPV4,
        value=value,
        extraction_source=ExtractionSource.REGEX,
        validation_status=ValidationStatus.VALID,
        confidence=confidence,
    )


class TestUpsertIOC:
    def test_creates_new_ioc_on_first_sighting(self, db_session):
        ioc, created = upsert_ioc(db_session, _candidate(), NOW)
        assert created is True
        assert ioc.first_seen == NOW
        assert ioc.last_seen == NOW

    def test_second_sighting_updates_not_duplicates(self, db_session):
        upsert_ioc(db_session, _candidate(), NOW)
        ioc, created = upsert_ioc(db_session, _candidate(), NOW + timedelta(hours=1))
        assert created is False
        assert _same_instant(ioc.last_seen, NOW + timedelta(hours=1))
        assert _same_instant(ioc.first_seen, NOW)
        assert len(db_session.scalars(select(IOC)).all()) == 1

    def test_earlier_sighting_moves_first_seen_backward(self, db_session):
        upsert_ioc(db_session, _candidate(), NOW)
        ioc, _ = upsert_ioc(db_session, _candidate(), NOW - timedelta(days=1))
        assert _same_instant(ioc.first_seen, NOW - timedelta(days=1))
        assert _same_instant(ioc.last_seen, NOW)

    def test_higher_confidence_sighting_raises_stored_confidence(self, db_session):
        upsert_ioc(db_session, _candidate(confidence=0.6), NOW)
        ioc, _ = upsert_ioc(db_session, _candidate(confidence=1.0), NOW)
        assert ioc.confidence == 1.0

    def test_lower_confidence_sighting_does_not_lower_stored_confidence(self, db_session):
        upsert_ioc(db_session, _candidate(confidence=1.0), NOW)
        ioc, _ = upsert_ioc(db_session, _candidate(confidence=0.6), NOW)
        assert ioc.confidence == 1.0

    def test_different_type_same_value_are_distinct_rows(self, db_session):
        upsert_ioc(
            db_session,
            ExtractedIOC(
                ioc_type=IOCType.IPV4,
                value="1234",
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=0.7,
            ),
            NOW,
        )
        upsert_ioc(
            db_session,
            ExtractedIOC(
                ioc_type=IOCType.USERNAME,
                value="1234",
                extraction_source=ExtractionSource.REGEX,
                validation_status=ValidationStatus.VALID,
                confidence=1.0,
            ),
            NOW,
        )
        assert len(db_session.scalars(select(IOC)).all()) == 2


class TestLinkEvent:
    def test_links_event_and_reports_new_link(self, db_session, make_event):
        event = make_event(SourceType.NETWORK, NOW, {"src_ip": "185.220.101.5"})
        ioc, _ = upsert_ioc(db_session, _candidate(), NOW)
        created = link_event(ioc, event)
        assert created is True
        assert event in ioc.events

    def test_relinking_same_event_is_a_noop(self, db_session, make_event):
        event = make_event(SourceType.NETWORK, NOW, {"src_ip": "185.220.101.5"})
        ioc, _ = upsert_ioc(db_session, _candidate(), NOW)
        link_event(ioc, event)
        created_again = link_event(ioc, event)
        assert created_again is False
        assert len(ioc.events) == 1
