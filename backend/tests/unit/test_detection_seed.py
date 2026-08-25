from sqlalchemy import select

from app.detection.registry import RULES
from app.detection.seed import ensure_detections_seeded
from app.models.detection import Detection


class TestEnsureDetectionsSeeded:
    def test_seeds_one_row_per_rule(self, db_session):
        result = ensure_detections_seeded(db_session)
        assert set(result.keys()) == {rule.rule_key for rule in RULES}
        assert db_session.scalars(select(Detection)).all().__len__() == len(RULES)

    def test_idempotent_on_repeated_calls(self, db_session):
        ensure_detections_seeded(db_session)
        ensure_detections_seeded(db_session)
        assert len(db_session.scalars(select(Detection)).all()) == len(RULES)

    def test_seeded_rows_carry_rule_metadata(self, db_session):
        result = ensure_detections_seeded(db_session)
        detection = result["ssh_brute_force"]
        assert detection.name == "SSH Brute Force"
        assert detection.enabled is True
        assert detection.config == {"failure_threshold": 10, "window_seconds": 300}
