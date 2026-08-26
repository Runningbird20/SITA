"""TODO.md Phase 11: 'Integration tests exercising the full pipeline
(ingest -> normalize -> detect -> extract IOCs -> correlate -> triage)
against synthetic datasets.' Every prior dataset-backed integration test
(Phase 3-5) stops at correlation; this is the one test that runs the
complete chain, including MITRE mapping and triage, against the real
checked-in multi-stage scenario — not ad-hoc test data.
"""

import json
from pathlib import Path

from sqlalchemy import select

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.ingestion.cli import load_jsonl
from app.ingestion.service import ingest_records
from app.ioc.pipeline import run_ioc_extraction
from app.llm.mock_provider import MockProvider
from app.llm.types import LLMConfig, RawCompletion
from app.mitre.loader import load_techniques
from app.mitre.pipeline import run_mitre_mapping
from app.models.analysis_result import AnalysisResult
from app.models.enums import AnalysisValidationStatus, MitreMappingSource, SourceType
from app.models.incident import Incident
from app.triage.pipeline import TASKS, run_triage

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASETS_DIR = REPO_ROOT / "data" / "synthetic_events"
SCENARIO_DIR = DATASETS_DIR / "scenarios" / "brute_force_to_lateral_movement"

_FAST_CONFIG = LLMConfig(model="test-model", max_retries=0, retry_backoff_seconds=0)

_VALID_COMPLETIONS = [
    RawCompletion(
        text=json.dumps(
            {
                "summary": "Multi-stage attack from 203.0.113.7.",
                "key_points": ["brute force from 203.0.113.7", "lateral movement"],
            }
        )
    ),
    RawCompletion(
        text=json.dumps({"explanation": "Escalated due to successful lateral movement."})
    ),
    RawCompletion(
        text=json.dumps(
            {
                "category": "lateral movement",
                "kill_chain_stage": "actions on objectives",
                "rationale": "PowerShell activity following brute force from 203.0.113.7.",
            }
        )
    ),
    RawCompletion(
        text=json.dumps(
            {"hypotheses": ["Compromised credentials from 203.0.113.7", "Insider threat"]}
        )
    ),
    RawCompletion(
        text=json.dumps({"steps": [{"text": "Isolate the affected host", "priority": "high"}]})
    ),
    RawCompletion(
        text=json.dumps(
            {
                "techniques": [
                    {
                        "technique_id": "T1110.001",
                        "technique_name": "Password Guessing",
                        "rationale": "Repeated auth failures.",
                    }
                ]
            }
        )
    ),
]


def _ingest(db_session, source_type: SourceType, path: Path) -> None:
    report = ingest_records(db=db_session, source_type=source_type, raw_records=load_jsonl(path))
    assert report.rejected == 0, f"{path} had unexpected rejections: {report.errors}"


class TestFullPipelineAgainstScenarioDataset:
    def test_ingest_through_triage_produces_a_fully_analyzed_incident(self, db_session):
        # 1. Ingest — the real checked-in multi-stage scenario, not ad-hoc data.
        _ingest(db_session, SourceType.AUTH, SCENARIO_DIR / "auth.jsonl")
        _ingest(db_session, SourceType.NETWORK, SCENARIO_DIR / "network.jsonl")
        _ingest(db_session, SourceType.ENDPOINT, SCENARIO_DIR / "endpoint.jsonl")
        _ingest(db_session, SourceType.DNS, SCENARIO_DIR / "dns.jsonl")
        db_session.commit()

        # 2. Detect
        detection_report = run_detection(db_session)
        db_session.commit()
        assert detection_report.alerts_created >= 3

        # 3. Extract IOCs
        ioc_report = run_ioc_extraction(db_session)
        db_session.commit()
        assert ioc_report.iocs_created > 0

        # 4. MITRE-map (vendored local dataset — no network dependency)
        load_techniques(db_session)
        db_session.commit()
        mitre_report = run_mitre_mapping(db_session)
        db_session.commit()
        assert mitre_report.alert_technique_mappings_created > 0

        # 5. Correlate — Phase 5's own DoD: everything lands in one incident.
        correlation_report = run_correlation(db_session)
        db_session.commit()
        assert correlation_report.incidents_created == 1

        incident = db_session.scalars(select(Incident)).one()
        assert len(incident.alerts) >= 3

        # 6. Triage — MockProvider stands in for the LLM; zero network calls.
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        triage_report = run_triage(db_session, provider=provider, config=_FAST_CONFIG)
        db_session.commit()

        assert triage_report.incidents_processed == 1
        assert triage_report.analysis_results_created == len(TASKS)

        # The final, fully-analyzed incident: deterministic findings and AI
        # analysis coexist, distinguishable by construction (never merged).
        results = db_session.scalars(
            select(AnalysisResult).where(AnalysisResult.incident_id == incident.id)
        ).all()
        assert len(results) == len(TASKS)
        assert all(r.validation_status == AnalysisValidationStatus.VALID for r in results)

        rule_mappings = [
            m
            for alert in incident.alerts
            for m in alert.mitre_mappings
            if m.source == MitreMappingSource.RULE
        ]
        assert rule_mappings, (
            "deterministic MITRE mappings should survive through to the final incident"
        )
