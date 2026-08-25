import json
from pathlib import Path

import pytest

from app.ingestion.cli import load_jsonl
from app.ingestion.service import ingest_records
from app.models.enums import SourceType

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = REPO_ROOT / "data" / "synthetic_events"


def _per_source_type_files() -> list[tuple[SourceType, Path]]:
    cases = []
    for source_dir in DATASETS_DIR.iterdir():
        if not source_dir.is_dir() or source_dir.name == "scenarios":
            continue
        source_type = SourceType(source_dir.name)
        for jsonl_file in sorted(source_dir.glob("*.jsonl")):
            cases.append((source_type, jsonl_file))
    return cases


def _scenario_files() -> list[tuple[SourceType, Path]]:
    cases = []
    scenarios_dir = DATASETS_DIR / "scenarios"
    for scenario_dir in scenarios_dir.iterdir():
        if not scenario_dir.is_dir():
            continue
        for jsonl_file in sorted(scenario_dir.glob("*.jsonl")):
            source_type = SourceType(jsonl_file.stem)
            cases.append((source_type, jsonl_file))
    return cases


PER_SOURCE_CASES = _per_source_type_files()
SCENARIO_CASES = _scenario_files()


class TestPerSourceTypeDatasets:
    @pytest.mark.parametrize(
        "source_type,path",
        PER_SOURCE_CASES,
        ids=[str(p.relative_to(REPO_ROOT)) for _, p in PER_SOURCE_CASES],
    )
    def test_file_ingests_with_zero_rejections(self, db_session, source_type, path):
        records = load_jsonl(path)
        assert records, f"{path} is empty"
        report = ingest_records(db=db_session, source_type=source_type, raw_records=records)
        assert report.rejected == 0, f"{path}: {report.errors}"
        assert report.accepted == len(records)


class TestScenarioDataset:
    @pytest.mark.parametrize(
        "source_type,path",
        SCENARIO_CASES,
        ids=[str(p.relative_to(REPO_ROOT)) for _, p in SCENARIO_CASES],
    )
    def test_scenario_file_ingests_with_zero_rejections(self, db_session, source_type, path):
        records = load_jsonl(path)
        assert records, f"{path} is empty"
        report = ingest_records(db=db_session, source_type=source_type, raw_records=records)
        assert report.rejected == 0, f"{path}: {report.errors}"

    def test_scenario_has_readme_and_expected_files(self):
        scenario_dir = DATASETS_DIR / "scenarios" / "brute_force_to_lateral_movement"
        assert (scenario_dir / "README.md").exists()
        for source_type in ("auth", "network", "endpoint", "dns"):
            assert (scenario_dir / f"{source_type}.jsonl").exists()

    def test_scenario_events_share_correlating_entities(self):
        scenario_dir = DATASETS_DIR / "scenarios" / "brute_force_to_lateral_movement"
        auth_records = [
            json.loads(line) for line in (scenario_dir / "auth.jsonl").read_text().splitlines()
        ]
        network_records = [
            json.loads(line) for line in (scenario_dir / "network.jsonl").read_text().splitlines()
        ]
        endpoint_records = [
            json.loads(line) for line in (scenario_dir / "endpoint.jsonl").read_text().splitlines()
        ]
        dns_records = [
            json.loads(line) for line in (scenario_dir / "dns.jsonl").read_text().splitlines()
        ]

        # web01's internal IP ties the auth stage to the network stage
        compromised_host_ip = "10.0.0.5"
        assert any(r["host"] == "web01.internal" for r in auth_records)
        assert any(r["src_ip"] == compromised_host_ip for r in network_records)

        # ws-07 ties the network stage to the endpoint and dns stages
        pivot_target_ip = "10.0.0.7"
        assert any(r["dst_ip"] == pivot_target_ip for r in network_records)
        assert all(r["host"] == "ws-07.internal" for r in endpoint_records)
        assert all(r["host"] == "ws-07.internal" for r in dns_records)
