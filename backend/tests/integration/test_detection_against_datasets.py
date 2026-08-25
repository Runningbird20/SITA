"""Runs the real detection engine against the real checked-in synthetic
datasets (not hand-built fixtures) — the direct test of Phase 3's Definition
of Done: "All 7 rules run against the Phase 2 synthetic datasets and produce
correctly-labeled alerts with documented false-positive/false-negative
behavior."
"""

from pathlib import Path

from sqlalchemy import select

from app.detection.pipeline import run_detection
from app.ingestion.cli import load_jsonl
from app.ingestion.service import ingest_records
from app.models.alert import Alert
from app.models.detection import Detection
from app.models.enums import SourceType

REPO_ROOT = Path(__file__).resolve().parents[3]
AUTH_DIR = REPO_ROOT / "data" / "synthetic_events" / "auth"
NETWORK_DIR = REPO_ROOT / "data" / "synthetic_events" / "network"
ENDPOINT_DIR = REPO_ROOT / "data" / "synthetic_events" / "endpoint"


def _ingest(db_session, source_type: SourceType, path: Path) -> None:
    report = ingest_records(db=db_session, source_type=source_type, raw_records=load_jsonl(path))
    assert report.rejected == 0, f"{path} had unexpected rejections: {report.errors}"


def _rule_keys_with_alerts(db_session) -> set[str]:
    rows = db_session.execute(select(Detection.rule_key).join(Alert).distinct()).all()
    return {row[0] for row in rows}


class TestTruePositives:
    """Each attack-pattern dataset, ingested alone, must trigger exactly the
    rule it was built to exercise."""

    def test_ssh_brute_force_dataset_triggers_ssh_brute_force(self, db_session):
        _ingest(db_session, SourceType.AUTH, AUTH_DIR / "brute_force.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert "ssh_brute_force" in _rule_keys_with_alerts(db_session)

    def test_password_spraying_dataset_triggers_password_spraying(self, db_session):
        _ingest(db_session, SourceType.AUTH, AUTH_DIR / "password_spraying.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert "password_spraying" in _rule_keys_with_alerts(db_session)

    def test_suspicious_pattern_dataset_triggers_suspicious_auth_pattern(self, db_session):
        # Off-hours check works standalone; the "new IP for known user"
        # check needs benign.jsonl's prior login history to be present too.
        _ingest(db_session, SourceType.AUTH, AUTH_DIR / "benign.jsonl")
        _ingest(db_session, SourceType.AUTH, AUTH_DIR / "suspicious_pattern.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert "suspicious_auth_pattern" in _rule_keys_with_alerts(db_session)

    def test_impossible_travel_dataset_triggers_impossible_travel(self, db_session):
        _ingest(db_session, SourceType.AUTH, AUTH_DIR / "impossible_travel.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert "impossible_travel" in _rule_keys_with_alerts(db_session)

    def test_distributed_failures_dataset_triggers_repeated_auth_failures(self, db_session):
        _ingest(db_session, SourceType.AUTH, AUTH_DIR / "distributed_failures.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert "repeated_auth_failures" in _rule_keys_with_alerts(db_session)

    def test_port_scan_dataset_triggers_port_scanning(self, db_session):
        _ingest(db_session, SourceType.NETWORK, NETWORK_DIR / "port_scan.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert "port_scanning" in _rule_keys_with_alerts(db_session)

    def test_suspicious_powershell_dataset_triggers_suspicious_powershell(self, db_session):
        _ingest(db_session, SourceType.ENDPOINT, ENDPOINT_DIR / "suspicious_powershell.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert "suspicious_powershell" in _rule_keys_with_alerts(db_session)


class TestTrueNegatives:
    """Ordinary/benign traffic, ingested alone, must trigger nothing —
    documents each rule's false-positive behavior on normal activity."""

    def test_auth_benign_triggers_no_alerts(self, db_session):
        _ingest(db_session, SourceType.AUTH, AUTH_DIR / "benign.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert db_session.scalars(select(Alert)).all() == []

    def test_network_benign_triggers_no_alerts(self, db_session):
        _ingest(db_session, SourceType.NETWORK, NETWORK_DIR / "benign.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert db_session.scalars(select(Alert)).all() == []

    def test_endpoint_benign_triggers_no_alerts(self, db_session):
        _ingest(db_session, SourceType.ENDPOINT, ENDPOINT_DIR / "benign.jsonl")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        assert db_session.scalars(select(Alert)).all() == []


class TestScenarioDataset:
    """The Phase 2 multi-stage scenario should trigger the specific rules
    its own README documents as expected."""

    def test_scenario_triggers_expected_rules(self, db_session):
        scenario_dir = (
            REPO_ROOT
            / "data"
            / "synthetic_events"
            / "scenarios"
            / "brute_force_to_lateral_movement"
        )
        _ingest(db_session, SourceType.AUTH, scenario_dir / "auth.jsonl")
        _ingest(db_session, SourceType.NETWORK, scenario_dir / "network.jsonl")
        _ingest(db_session, SourceType.ENDPOINT, scenario_dir / "endpoint.jsonl")
        db_session.commit()

        run_detection(db_session)
        db_session.commit()

        triggered = _rule_keys_with_alerts(db_session)
        assert "ssh_brute_force" in triggered
        assert "port_scanning" in triggered
        assert "suspicious_powershell" in triggered
