import json
from datetime import timedelta

from sqlalchemy import select

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.ioc.pipeline import run_ioc_extraction
from app.llm.exceptions import LLMProviderError, LLMTimeoutError
from app.llm.mock_provider import MockProvider
from app.llm.registry import default_llm_config
from app.llm.types import LLMConfig, RawCompletion
from app.models.analysis_result import AnalysisResult
from app.models.associations import AlertMitreMapping
from app.models.enums import (
    AlertStatus,
    AnalysisTaskType,
    AnalysisValidationStatus,
    IncidentStatus,
    MitreMappingSource,
)
from app.models.incident import Incident
from app.models.mitre import MITRETechnique
from app.models.recommendation import Recommendation
from app.triage.pipeline import TASKS, run_triage
from tests.conftest import BRUTE_FORCE_NOW

_VALID_COMPLETIONS = [
    RawCompletion(
        text=json.dumps(
            {
                "summary": "Brute force attempt from 198.51.100.1.",
                "key_points": ["10 failed logins from 198.51.100.1"],
            }
        )
    ),
    RawCompletion(text=json.dumps({"explanation": "High severity due to repeated failures."})),
    RawCompletion(
        text=json.dumps(
            {
                "category": "credential access",
                "kill_chain_stage": "initial access",
                "rationale": "Password guessing from 198.51.100.1.",
            }
        )
    ),
    RawCompletion(
        text=json.dumps(
            {
                "hypotheses": [
                    "Targeted attack from 198.51.100.1",
                    "Compromised credential reuse",
                ]
            }
        )
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

_FAST_CONFIG = LLMConfig(model="test-model", max_retries=0, retry_backoff_seconds=0)


def _make_incident(db_session, brute_force_events) -> Incident:
    brute_force_events()
    db_session.commit()
    run_detection(db_session)
    db_session.commit()
    # IOC extraction, matching DEF.md's recommended pipeline order
    # (detect -> extract IOCs -> correlate) — without it, `real_identifiers()`
    # only ever sees the host entity, never the attacker IP, which the
    # grounding-aware retry in run_triage() then correctly (but
    # inconveniently, for a fixture that doesn't mention the IP) flags as
    # ungrounded.
    run_ioc_extraction(db_session)
    db_session.commit()
    run_correlation(db_session)
    db_session.commit()
    return db_session.scalars(select(Incident)).one()


class TestRunTriage:
    def test_creates_one_analysis_result_per_task(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
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

    def test_investigation_steps_creates_recommendations(self, db_session, brute_force_events):
        _make_incident(db_session, brute_force_events)
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
        self, db_session, brute_force_events
    ):
        _make_incident(db_session, brute_force_events)
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

    def test_mitre_suggestion_with_local_technique_creates_mapping(
        self, db_session, brute_force_events
    ):
        incident = _make_incident(db_session, brute_force_events)
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

    def test_rerun_without_force_is_idempotent(self, db_session, brute_force_events):
        _make_incident(db_session, brute_force_events)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        second_provider = MockProvider(responses=list(_VALID_COMPLETIONS))
        report = run_triage(db_session, provider=second_provider, config=default_llm_config())
        db_session.commit()

        assert report.analysis_results_created == 0
        assert report.analysis_results_skipped == len(TASKS)
        assert len(db_session.scalars(select(AnalysisResult)).all()) == len(TASKS)

    def test_force_regenerates_every_task(self, db_session, brute_force_events):
        _make_incident(db_session, brute_force_events)
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

    def test_invalid_output_creates_no_recommendation(self, db_session, brute_force_events):
        _make_incident(db_session, brute_force_events)
        provider = MockProvider(responses=RawCompletion(text="not json"))

        run_triage(db_session, provider=provider, config=_FAST_CONFIG)
        db_session.commit()

        results = db_session.scalars(select(AnalysisResult)).all()
        assert all(r.validation_status == AnalysisValidationStatus.INVALID for r in results)
        assert all(r.confidence is None for r in results)
        assert db_session.scalars(select(Recommendation)).all() == []
        assert db_session.scalars(select(AlertMitreMapping)).all() == []

    def test_incident_id_scopes_to_one_incident(self, db_session, brute_force_events):
        incident_a = _make_incident(db_session, brute_force_events)
        brute_force_events(source_ip="203.0.113.9", dest_host="app02.internal")
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

    def test_since_filters_incidents_by_last_activity(self, db_session, brute_force_events):
        _make_incident(db_session, brute_force_events)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))

        report = run_triage(
            db_session,
            since=BRUTE_FORCE_NOW + timedelta(days=1),
            provider=provider,
            config=default_llm_config(),
        )
        db_session.commit()

        assert report.incidents_processed == 0
        assert db_session.scalars(select(AnalysisResult)).all() == []


class TestGroundingAwareRetry:
    """Post-roadmap addition (WHATNEXT.md 'AI quality' item, DEF.md § 8
    AnalysisResult 'Grounding-aware retry'): a VALID but ungrounded
    incident_summary/investigation_hypothesis/attack_classification
    response is regenerated once before being persisted.
    """

    def test_ungrounded_first_response_is_retried_and_replaced(
        self, db_session, brute_force_events
    ):
        _make_incident(db_session, brute_force_events)
        # incident_summary: first attempt mentions nothing real, second
        # (the retry) mentions the real attacker IP.
        completions = [
            RawCompletion(text=json.dumps({"summary": "Suspicious activity.", "key_points": []})),
            RawCompletion(
                text=json.dumps(
                    {"summary": "Attack from 198.51.100.1.", "key_points": ["198.51.100.1"]}
                )
            ),
            *_VALID_COMPLETIONS[1:],
        ]
        provider = MockProvider(responses=completions)

        run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        result = db_session.scalars(
            select(AnalysisResult).where(
                AnalysisResult.task_type == AnalysisTaskType.INCIDENT_SUMMARY
            )
        ).one()
        assert result.grounding_retry_used is True
        assert result.validation_status == AnalysisValidationStatus.VALID
        assert result.parsed_output["summary"] == "Attack from 198.51.100.1."

    def test_grounded_first_response_is_not_retried(self, db_session, brute_force_events):
        _make_incident(db_session, brute_force_events)
        provider = MockProvider(responses=list(_VALID_COMPLETIONS))

        run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        result = db_session.scalars(
            select(AnalysisResult).where(
                AnalysisResult.task_type == AnalysisTaskType.INCIDENT_SUMMARY
            )
        ).one()
        assert result.grounding_retry_used is False
        assert result.parsed_output["summary"] == "Brute force attempt from 198.51.100.1."

    def test_invalid_retry_falls_back_to_the_original_ungrounded_response(
        self, db_session, brute_force_events
    ):
        _make_incident(db_session, brute_force_events)
        completions = [
            RawCompletion(text=json.dumps({"summary": "Suspicious activity.", "key_points": []})),
            RawCompletion(text="not json"),  # the retry itself fails validation
            *_VALID_COMPLETIONS[1:],
        ]
        provider = MockProvider(responses=completions)

        run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        result = db_session.scalars(
            select(AnalysisResult).where(
                AnalysisResult.task_type == AnalysisTaskType.INCIDENT_SUMMARY
            )
        ).one()
        assert result.grounding_retry_used is True
        assert result.validation_status == AnalysisValidationStatus.VALID
        assert result.parsed_output["summary"] == "Suspicious activity."

    def test_non_groundable_task_types_are_never_retried(self, db_session, brute_force_events):
        # severity_explanation, investigation_steps, and mitre_suggestion
        # have no groundable free-text field checked here — an ungrounded
        # explanation must not trigger a retry.
        _make_incident(db_session, brute_force_events)
        completions = list(_VALID_COMPLETIONS)
        completions[1] = RawCompletion(
            text=json.dumps({"explanation": "Generic severity explanation, no specifics."})
        )
        provider = MockProvider(responses=completions)

        run_triage(db_session, provider=provider, config=default_llm_config())
        db_session.commit()

        result = db_session.scalars(
            select(AnalysisResult).where(
                AnalysisResult.task_type == AnalysisTaskType.SEVERITY_EXPLANATION
            )
        ).one()
        assert result.grounding_retry_used is False


class TestLLMUnavailableDegradesGracefully:
    """TODO.md Phase 11: 'Failure-case tests... (LLM unavailable) confirming
    graceful degradation, not crashes.' Phase 6 already proves generate()
    itself never raises; this proves the same holds one layer up, at the
    pipeline run real callers actually invoke, and that the incident's
    deterministic data is completely unaffected by the LLM being down.
    """

    def test_provider_error_on_every_call_does_not_raise_and_incident_stays_intact(
        self, db_session, brute_force_events
    ):
        incident = _make_incident(db_session, brute_force_events)
        original_status = incident.status
        original_severity = incident.severity
        alert_count_before = len(incident.alerts)

        provider = MockProvider(raises=LLMProviderError("ollama unreachable"))

        report = run_triage(db_session, provider=provider, config=_FAST_CONFIG)
        db_session.commit()

        assert report.analysis_results_created == len(TASKS)
        results = db_session.scalars(select(AnalysisResult)).all()
        assert all(r.validation_status == AnalysisValidationStatus.PROVIDER_ERROR for r in results)
        assert all(r.confidence is None for r in results)
        assert db_session.scalars(select(Recommendation)).all() == []
        assert db_session.scalars(select(AlertMitreMapping)).all() == []

        # The incident and its alerts are exactly as deterministic detection
        # and correlation left them — untouched by the LLM being down.
        db_session.refresh(incident)
        assert incident.status == original_status
        assert incident.severity == original_severity
        assert len(incident.alerts) == alert_count_before
        assert incident.alerts[0].status == AlertStatus.NEW
        assert incident.status == IncidentStatus.OPEN

    def test_timeout_on_every_call_does_not_raise(self, db_session, brute_force_events):
        _make_incident(db_session, brute_force_events)
        provider = MockProvider(raises=LLMTimeoutError("timed out after 30s"))

        report = run_triage(db_session, provider=provider, config=_FAST_CONFIG)
        db_session.commit()

        assert report.analysis_results_created == len(TASKS)
        results = db_session.scalars(select(AnalysisResult)).all()
        assert all(r.validation_status == AnalysisValidationStatus.TIMEOUT for r in results)
