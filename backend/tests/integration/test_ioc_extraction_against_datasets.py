"""Runs the real IOC extraction pipeline against the real checked-in
synthetic datasets — the direct test of Phase 4's Definition of Done:
"All 7 IOC types are deterministically extracted and validated ... against
a labeled fixture set."
"""

from pathlib import Path

from sqlalchemy import select

from app.detection.pipeline import run_detection
from app.ingestion.cli import load_jsonl
from app.ingestion.service import ingest_records
from app.ioc.pipeline import run_ioc_extraction
from app.models.enums import IOCType, SourceType
from app.models.ioc import IOC

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = REPO_ROOT / "data" / "synthetic_events"


def _ingest(db_session, source_type: SourceType, path: Path) -> None:
    report = ingest_records(db=db_session, source_type=source_type, raw_records=load_jsonl(path))
    assert report.rejected == 0, f"{path} had unexpected rejections: {report.errors}"


def _ioc_values(db_session, ioc_type: IOCType) -> set[str]:
    return set(db_session.scalars(select(IOC.value).where(IOC.ioc_type == ioc_type)).all())


class TestAllSevenIOCTypesExtracted:
    """One dataset combination per IOC type, proving each type is genuinely
    reachable through the real pipeline, not just unit-tested in isolation."""

    def test_ipv4_extracted_from_network_events(self, db_session):
        _ingest(db_session, SourceType.NETWORK, DATASETS_DIR / "network" / "port_scan.jsonl")
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert "10.0.0.5" in _ioc_values(db_session, IOCType.IPV4)

    def test_ipv6_extracted_from_network_events(self, db_session):
        _ingest(db_session, SourceType.NETWORK, DATASETS_DIR / "network" / "ipv6_traffic.jsonl")
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert "2001:db8:1234:5678::10" in _ioc_values(db_session, IOCType.IPV6)

    def test_domain_extracted_from_dns_events(self, db_session):
        _ingest(db_session, SourceType.DNS, DATASETS_DIR / "dns" / "suspicious_domain.jsonl")
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert "cdn-update-service.example" in _ioc_values(db_session, IOCType.DOMAIN)

    def test_url_extracted_from_endpoint_command_line(self, db_session):
        _ingest(
            db_session, SourceType.ENDPOINT, DATASETS_DIR / "endpoint" / "ioc_rich_activity.jsonl"
        )
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert "http://185.220.101.5/payload.bin" in _ioc_values(db_session, IOCType.URL)

    def test_file_hash_extracted_from_endpoint_command_line(self, db_session):
        _ingest(
            db_session, SourceType.ENDPOINT, DATASETS_DIR / "endpoint" / "ioc_rich_activity.jsonl"
        )
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        expected = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert expected in _ioc_values(db_session, IOCType.FILE_HASH_SHA256)

    def test_email_extracted_from_web_path(self, db_session):
        _ingest(db_session, SourceType.WEB, DATASETS_DIR / "web" / "ioc_rich_requests.jsonl")
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert "victim@example.com" in _ioc_values(db_session, IOCType.EMAIL)

    def test_username_extracted_from_auth_events(self, db_session):
        _ingest(db_session, SourceType.AUTH, DATASETS_DIR / "auth" / "brute_force.jsonl")
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert "admin" in _ioc_values(db_session, IOCType.USERNAME)


class TestFalsePositiveBehaviorOnBenignData:
    """Benign traffic shouldn't produce noise: no private IPs as IOCs from
    free-text scanning, no internal hostnames misread as domains."""

    def test_endpoint_benign_produces_no_url_or_hash_iocs(self, db_session):
        _ingest(db_session, SourceType.ENDPOINT, DATASETS_DIR / "endpoint" / "benign.jsonl")
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert _ioc_values(db_session, IOCType.URL) == set()
        assert _ioc_values(db_session, IOCType.FILE_HASH_MD5) == set()
        assert _ioc_values(db_session, IOCType.FILE_HASH_SHA256) == set()

    def test_web_benign_produces_no_email_iocs(self, db_session):
        _ingest(db_session, SourceType.WEB, DATASETS_DIR / "web" / "benign.jsonl")
        db_session.commit()
        run_ioc_extraction(db_session)
        db_session.commit()
        assert _ioc_values(db_session, IOCType.EMAIL) == set()


class TestScenarioDataset:
    def test_scenario_iocs_link_to_the_alerts_they_belong_to(self, db_session):
        scenario_dir = DATASETS_DIR / "scenarios" / "brute_force_to_lateral_movement"
        _ingest(db_session, SourceType.AUTH, scenario_dir / "auth.jsonl")
        _ingest(db_session, SourceType.NETWORK, scenario_dir / "network.jsonl")
        _ingest(db_session, SourceType.ENDPOINT, scenario_dir / "endpoint.jsonl")
        _ingest(db_session, SourceType.DNS, scenario_dir / "dns.jsonl")
        db_session.commit()

        run_detection(db_session)
        db_session.commit()
        report = run_ioc_extraction(db_session)
        db_session.commit()

        assert report.alert_links_created > 0
        # The attacker's external IP should be a tracked IOC, linked to the
        # ssh_brute_force alert specifically.
        from app.models.alert import Alert
        from app.models.detection import Detection

        brute_force_alert = db_session.scalars(
            select(Alert).join(Detection).where(Detection.rule_key == "ssh_brute_force")
        ).one()
        ioc_values = {ioc.value for ioc in brute_force_alert.iocs}
        assert "203.0.113.7" in ioc_values
