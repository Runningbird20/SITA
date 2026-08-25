"""Runs the real correlation pipeline against the real checked-in synthetic
datasets — the direct test of Phase 5's Definition of Done: "Alerts from
the multi-stage attack scenario correlate into one incident ... unrelated
alerts remain separate."
"""

from pathlib import Path

from sqlalchemy import select

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.ingestion.cli import load_jsonl
from app.ingestion.service import ingest_records
from app.ioc.pipeline import run_ioc_extraction
from app.models.enums import SourceType
from app.models.incident import Incident

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = REPO_ROOT / "data" / "synthetic_events"
SCENARIO_DIR = DATASETS_DIR / "scenarios" / "brute_force_to_lateral_movement"


def _ingest(db_session, source_type: SourceType, path: Path) -> None:
    report = ingest_records(db=db_session, source_type=source_type, raw_records=load_jsonl(path))
    assert report.rejected == 0, f"{path} had unexpected rejections: {report.errors}"


def _run_full_pipeline(db_session) -> None:
    run_detection(db_session)
    db_session.commit()
    run_ioc_extraction(db_session)
    db_session.commit()
    run_correlation(db_session)
    db_session.commit()


class TestScenarioMergesIntoOneIncident:
    def test_all_scenario_alerts_land_in_one_incident(self, db_session):
        _ingest(db_session, SourceType.AUTH, SCENARIO_DIR / "auth.jsonl")
        _ingest(db_session, SourceType.NETWORK, SCENARIO_DIR / "network.jsonl")
        _ingest(db_session, SourceType.ENDPOINT, SCENARIO_DIR / "endpoint.jsonl")
        _ingest(db_session, SourceType.DNS, SCENARIO_DIR / "dns.jsonl")
        db_session.commit()

        _run_full_pipeline(db_session)

        incidents = db_session.scalars(select(Incident)).all()
        assert len(incidents) == 1

        incident = incidents[0]
        assert "SSH Brute Force" in incident.title
        assert "Port Scanning" in incident.title
        assert "Suspicious PowerShell Activity" in incident.title
        assert incident.severity in {"high", "critical"}
        assert len(incident.alerts) >= 3


class TestUnrelatedAlertsStaySeparate:
    def test_standalone_brute_force_does_not_join_the_scenario_incident(self, db_session):
        _ingest(db_session, SourceType.AUTH, SCENARIO_DIR / "auth.jsonl")
        _ingest(db_session, SourceType.NETWORK, SCENARIO_DIR / "network.jsonl")
        _ingest(db_session, SourceType.ENDPOINT, SCENARIO_DIR / "endpoint.jsonl")
        _ingest(db_session, SourceType.DNS, SCENARIO_DIR / "dns.jsonl")
        # A different host, different attacker IP, several hours later —
        # nothing should tie it to the scenario.
        _ingest(db_session, SourceType.AUTH, DATASETS_DIR / "auth" / "brute_force.jsonl")
        db_session.commit()

        _run_full_pipeline(db_session)

        incidents = db_session.scalars(select(Incident)).all()
        assert len(incidents) == 2

        titles = {incident.title for incident in incidents}
        assert any("SSH Brute Force" in t and "Port Scanning" in t for t in titles)
        # The standalone brute-force alert's own incident must not also
        # contain the scenario's signature rules.
        standalone_title = next(t for t in titles if "Port Scanning" not in t)
        assert "SSH Brute Force" in standalone_title

    def test_port_scan_fixture_attacker_ip_is_not_treated_as_a_host_entity(self, db_session):
        # Regression test: 198.51.100.88 (the port-scan fixture's attacker
        # IP) is an RFC 5737 documentation address, which Python's
        # ipaddress.is_private incorrectly flags as private. It must not
        # become a host Entity.
        from sqlalchemy import select as sa_select

        from app.models.entity import Entity

        _ingest(db_session, SourceType.NETWORK, DATASETS_DIR / "network" / "port_scan.jsonl")
        db_session.commit()
        _run_full_pipeline(db_session)

        identifiers = set(db_session.scalars(sa_select(Entity.identifier)).all())
        assert "198.51.100.88" not in identifiers
        # 10.0.0.5 is a known alias (see host_identity.py) and canonicalizes
        # to its hostname rather than appearing as a raw-IP entity.
        assert "web01.internal" in identifiers
        assert "10.0.0.5" not in identifiers
