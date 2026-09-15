from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.enums import AlertStatus, DetectionCategory, Severity
from app.rule_tuning.analyzer import compute_tuning_suggestions

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)


def _session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _make_detection(db, rule_key="ssh_brute_force", config=None) -> Detection:
    detection = Detection(
        rule_key=rule_key,
        name="SSH Brute Force",
        description="Repeated auth failures.",
        category=DetectionCategory.AUTHENTICATION,
        default_severity=Severity.HIGH,
        enabled=True,
        config=config,
    )
    db.add(detection)
    db.flush()
    return detection


def _make_alerts(db, detection: Detection, count: int, false_positive_count: int) -> None:
    for i in range(count):
        status = AlertStatus.FALSE_POSITIVE if i < false_positive_count else AlertStatus.NEW
        db.add(
            Alert(
                detection_id=detection.id,
                fingerprint=f"fp-{detection.rule_key}-{i}",
                severity=Severity.HIGH,
                confidence=0.8,
                status=status,
                rationale="test",
                severity_factors={},
                first_event_at=NOW,
                last_event_at=NOW,
            )
        )
    db.flush()


class TestComputeTuningSuggestions:
    def test_high_false_positive_rate_yields_suggestion(self):
        session_factory = _session_factory()
        with session_factory() as db:
            detection = _make_detection(db, config={"failure_threshold": 10})
            _make_alerts(db, detection, count=10, false_positive_count=6)
            db.commit()

            suggestions = compute_tuning_suggestions(db)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.rule_key == "ssh_brute_force"
        assert s.total_alerts == 10
        assert s.false_positive_count == 6
        assert s.false_positive_rate == 0.6
        assert s.threshold_key == "failure_threshold"
        assert s.current_threshold_value == 10
        assert s.suggested_threshold_value == 12
        assert "failure_threshold" in s.rationale

    def test_below_min_sample_size_is_skipped(self):
        session_factory = _session_factory()
        with session_factory() as db:
            detection = _make_detection(db, config={"failure_threshold": 10})
            _make_alerts(db, detection, count=5, false_positive_count=5)
            db.commit()

            suggestions = compute_tuning_suggestions(db, min_sample_size=10)

        assert suggestions == []

    def test_below_false_positive_rate_threshold_is_skipped(self):
        session_factory = _session_factory()
        with session_factory() as db:
            detection = _make_detection(db, config={"failure_threshold": 10})
            _make_alerts(db, detection, count=10, false_positive_count=2)
            db.commit()

            suggestions = compute_tuning_suggestions(db)

        assert suggestions == []

    def test_rule_with_no_primary_threshold_key_is_skipped(self):
        session_factory = _session_factory()
        with session_factory() as db:
            detection = _make_detection(db, rule_key="privilege_escalation", config={})
            _make_alerts(db, detection, count=10, false_positive_count=8)
            db.commit()

            suggestions = compute_tuning_suggestions(db)

        assert suggestions == []

    def test_no_detection_row_for_rule_is_skipped(self):
        session_factory = _session_factory()
        with session_factory() as db:
            suggestions = compute_tuning_suggestions(db)

        assert suggestions == []

    def test_falls_back_to_default_config_when_detection_config_is_none(self):
        session_factory = _session_factory()
        with session_factory() as db:
            detection = _make_detection(db, config=None)
            _make_alerts(db, detection, count=10, false_positive_count=6)
            db.commit()

            suggestions = compute_tuning_suggestions(db)

        assert len(suggestions) == 1
        assert suggestions[0].current_threshold_value == 10

    def test_float_threshold_rounds_to_four_places(self):
        session_factory = _session_factory()
        with session_factory() as db:
            detection = _make_detection(
                db, rule_key="anomalous_event_volume", config={"z_score_threshold": 3.0}
            )
            _make_alerts(db, detection, count=10, false_positive_count=7)
            db.commit()

            suggestions = compute_tuning_suggestions(db)

        assert len(suggestions) == 1
        s = suggestions[0]
        assert s.threshold_key == "z_score_threshold"
        assert s.suggested_threshold_value == 3.6
