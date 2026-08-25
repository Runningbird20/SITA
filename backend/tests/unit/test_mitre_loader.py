import json

from sqlalchemy import select

from app.mitre.loader import DEFAULT_DATASET_PATH, load_techniques
from app.models.mitre import MITRETechnique


class TestLoadTechniques:
    def test_loads_the_real_vendored_dataset(self, db_session):
        report = load_techniques(db_session)
        db_session.commit()

        raw = json.loads(DEFAULT_DATASET_PATH.read_text())
        assert report.dataset_version == raw["dataset_version"]
        assert report.techniques_created == len(raw["techniques"])
        assert report.techniques_updated == 0

        rows = db_session.scalars(select(MITRETechnique)).all()
        assert len(rows) == len(raw["techniques"])
        assert {r.technique_id for r in rows} == {t["technique_id"] for t in raw["techniques"]}

    def test_idempotent_on_repeated_calls(self, db_session):
        load_techniques(db_session)
        db_session.commit()

        report = load_techniques(db_session)
        db_session.commit()

        assert report.techniques_created == 0
        assert report.techniques_updated == 0

    def test_loads_and_updates_from_a_custom_dataset(self, db_session, tmp_path):
        dataset_path = tmp_path / "techniques.json"
        dataset_path.write_text(
            json.dumps(
                {
                    "dataset_version": "test-v1",
                    "techniques": [
                        {
                            "technique_id": "T9999",
                            "name": "Test Technique",
                            "tactic": "test-tactic",
                            "description": "A technique used only in this test.",
                        }
                    ],
                }
            )
        )

        first = load_techniques(db_session, path=dataset_path)
        db_session.commit()
        assert first.techniques_created == 1
        assert first.techniques_updated == 0

        dataset_path.write_text(
            json.dumps(
                {
                    "dataset_version": "test-v2",
                    "techniques": [
                        {
                            "technique_id": "T9999",
                            "name": "Renamed Test Technique",
                            "tactic": "test-tactic",
                            "description": "A technique used only in this test.",
                        }
                    ],
                }
            )
        )
        second = load_techniques(db_session, path=dataset_path)
        db_session.commit()
        assert second.techniques_created == 0
        assert second.techniques_updated == 1

        technique = db_session.scalars(
            select(MITRETechnique).where(MITRETechnique.technique_id == "T9999")
        ).one()
        assert technique.name == "Renamed Test Technique"
        assert technique.dataset_version == "test-v2"
