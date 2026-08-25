import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.llm.mock_provider import MockProvider
from app.llm.registry import default_llm_config
from app.llm.types import LLMConfig, RawCompletion
from app.models.analysis_result import AnalysisResult
from app.models.associations import AlertMitreMapping
from app.models.enums import (
    AnalysisTaskType,
    AnalysisValidationStatus,
    MitreMappingSource,
    SourceType,
)
from app.models.incident import Incident
from app.models.mitre import MITRETechnique
from app.models.recommendation import Recommendation
from app.triage.pipeline import TASKS, run_triage

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)

_VALID_COMPLETIONS = [
    RawCompletion(
        text=json.dumps({"summary": "Brute force attempt.", "key_points": ["10 failed logins"]})
    ),
    RawCompletion(text=json.dumps({"explanation": "High severity due to repeated failures."})),
    RawCompletion(
        text=json.dumps(
            {
                "category": "credential access",
                "kill_chain_stage": "initial access",
                "rationale": "Password guessing.",
            }
        )
    ),
    RawCompletion(
        text=json.dumps({"hypotheses": ["Targeted attack", "Compromised credential reuse"]})
    ),
    RawCompletion(
        text=json.dumps(
            {
                "steps": [
                    {"text": "Review auth logs for the source IP", "priority": "high"},
                    {"text": "Check for lateral movement", "priority": "medium"},
                ]
            }
        )
    ),
    RawCompletion(
        text=json.dumps(
            {
                "techniques": [
                    {
                        "technique_id": "T1110.001",
                        "technique_name": "Password Guessing",
                        "rationale": "Repeated failed logins.",
                    }
                ]
            }
        )
    ),
]


def _brute_force_events(make_event, source_ip="198.51.100.1", dest_host="db01.internal"):
    for i in range(10):
        make_event(
            SourceType.AUTH,
            NOW + timedelta(seconds=i * 20),
            {
                "event_result": "failure",
                "username": "admin",
                "source_ip": source_ip,
                "dest_host": dest_host,
                "auth_method": "password",
            },
            host=dest_host,
        )


def _make_incident(db_session, make_event) -> Incident:
    _brute_force_events(make_event)
    db_session.commit()
    run_detection(db_session)
    db_session.commit()
    run_correlation(db_session)
    db_session.commit()
    return db_session.scalars(select(Incident)).one()


class TestRunTriage:
    def test_creates_one_analysis_result_per_task(self, db_session, make_event):
        incident = _make_incident(db_session, make_event)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))

        report = run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        results = db_session.scalars(select(AnalysisResult)).all()
        assert len(results) == len(TASKS)
        assert {r.task_type for r in results} == {t.task_type for t in TASKS}
        assert all(r.incident_id == incident.id for r in results)
        assert all(r.alert_id is None for r in results)
        assert all(r.validation_status == AnalysisValidationStatus.VALID for r in results)
        assert report.analysis_results_created == len(TASKS)
        assert report.analysis_results_skipped == 0
        assert report.incidents_processed == 1

    def test_investigation_steps_creates_recommendations(self, db_session, make_event):
        _make_incident(db_session, make_event)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))

        report = run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        recs = db_session.scalars(select(Recommendation)).all()
        assert len(recs) == 2
        assert report.recommendations_created == 2
        assert {str(r.priority) for r in recs} == {"high", "medium"}
        result = db_session.scalars(
            select(AnalysisResult).where(
                AnalysisResult.task_type == AnalysisTaskType.INVESTIGATION_STEPS
            )
        ).one()
        assert all(r.analysis_result_id == result.id for r in recs)
        assert all(str(r.source) == "llm" for r in recs)

    def test_mitre_suggestion_without_local_technique_creates_no_mapping(
        self, db_session, make_event
    ):
        _make_incident(db_session, make_event)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))

        report = run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        assert db_session.scalars(select(AlertMitreMapping)).all() == []
        assert report.mitre_mappings_created == 0
        # The raw suggestion is still preserved even though no FK row was made.
        result = db_session.scalars(
            select(AnalysisResult).where(
                AnalysisResult.task_type == AnalysisTaskType.MITRE_SUGGESTION
            )
        ).one()
        assert result.parsed_output["techniques"][0]["technique_id"] == "T1110.001"

    def test_mitre_suggestion_with_local_technique_creates_mapping(self, db_session, make_event):
        incident = _make_incident(db_session, make_event)
        db_session.add(
            MITRETechnique(
                technique_id="T1110.001",
                name="Password Guessing",
                tactic="credential-access",
                description="Brute forcing passwords.",
                dataset_version="test",
            )
        )
        db_session.commit()
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))

        report = run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        mappings = db_session.scalars(select(AlertMitreMapping)).all()
        assert len(mappings) == len(incident.alerts)
        assert all(m.source == MitreMappingSource.LLM for m in mappings)
        assert report.mitre_mappings_created == len(incident.alerts)

    def test_rerun_without_force_is_idempotent(self, db_session, make_event):
        _make_incident(db_session, make_event)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        second_provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        report = run_triage(db_session, provider=second_provider, config=default_llm_config())
        db_session.commit()

        assert report.analysis_results_created == 0
        assert report.analysis_results_skipped == len(TASKS)
        assert len(db_session.scalars(select(AnalysisResult)).all()) == len(TASKS)

    def test_force_regenerates_every_task(self, db_session, make_event):
        _make_incident(db_session, make_event)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        second_provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        report = run_triage(
            db_session, provider=second_provider, config=default_llm_config(), force=True
        )
        db_session.commit()

        assert report.analysis_results_created == len(TASKS)
        assert len(db_session.scalars(select(AnalysisResult)).all()) == 2 * len(TASKS)

    def test_invalid_output_creates_no_recommendation(self, db_session, make_event):
        _make_incident(db_session, make_event)
        provider = MockProvider(responses=RawCompletion(text="not json"))
        fast_config = LLMConfig(model="test-model", max_retries=0, retry_backoff_seconds=0)

        run_triage(db_session, provider=provider, config=fast_config)
        db_session.commit()

        results = db_session.scalars(select(AnalysisResult)).all()
        assert all(r.validation_status == AnalysisValidationStatus.INVALID for r in results)
        assert all(r.confidence is None for r in results)
        assert db_session.scalars(select(Recommendation)).all() == []
        assert db_session.scalars(select(AlertMitreMapping)).all() == []

    def test_incident_id_scopes_to_one_incident(self, db_session, make_event):
        incident_a = _make_incident(db_session, make_event)
        _brute_force_events(make_event, source_ip="203.0.113.9", dest_host="app02.internal")
        db_session.commit()
        run_detection(db_session)
        db_session.commit()
        run_correlation(db_session)
        db_session.commit()
        assert len(db_session.scalars(select(Incident)).all()) == 2

        provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        report = run_triage(
            db_session, incident_id=incident_a.id, provider=provider, config=default_llm_config()
        )
        db_session.commit()

        assert report.incidents_processed == 1
        results = db_session.scalars(select(AnalysisResult)).all()
        assert all(r.incident_id == incident_a.id for r in results)

    def test_since_filters_incidents_by_last_activity(self, db_session, make_event):
        _make_incident(db_session, make_event)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))

        report = run_triage(
            db_session,
            since=NOW + timedelta(days=1),
            provider=provider,
            config=default_llm_config(),
        )
        db_session.commit()

        assert report.incidents_processed == 0
        assert db_session.scalars(select(AnalysisResult)).all() == []
