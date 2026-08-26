import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.correlation.pipeline import run_correlation
from app.detection.pipeline import run_detection
from app.evaluation.ai_grounding import (
    evaluate_grounding,
    mentions_a_real_identifier,
    real_identifiers,
)
from app.ioc.pipeline import run_ioc_extraction
from app.models.analysis_result import AnalysisResult
from app.models.enums import AnalysisTaskType, AnalysisValidationStatus
from app.models.incident import Incident


def _make_incident(db_session, brute_force_events) -> Incident:
    brute_force_events()
    db_session.commit()
    run_detection(db_session)
    db_session.commit()
    run_ioc_extraction(db_session)
    db_session.commit()
    run_correlation(db_session)
    db_session.commit()
    return db_session.scalars(select(Incident)).one()


def _result(task_type: AnalysisTaskType, parsed_output: dict) -> AnalysisResult:
    # Transient, never added to the session — evaluate_grounding() only
    # reads attributes off these, no FK/DB round-trip needed.
    return AnalysisResult(
        id=uuid.uuid4(),
        task_type=task_type,
        provider="mock",
        model="test-model",
        prompt_version="v1",
        raw_output="{}",
        parsed_output=parsed_output,
        validation_status=AnalysisValidationStatus.VALID,
        confidence=1.0,
        latency_ms=0,
        created_at=datetime.now(UTC),
    )


class TestRealIdentifiers:
    def test_includes_ioc_values_and_host_entity(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
        identifiers = real_identifiers(incident)
        assert "198.51.100.1" in identifiers
        assert "admin" in identifiers
        assert "db01.internal" in identifiers


class TestMentionsARealIdentifier:
    def test_true_when_text_contains_an_identifier(self):
        assert mentions_a_real_identifier("Traffic from 198.51.100.1 was blocked", {"198.51.100.1"})

    def test_case_insensitive(self):
        assert mentions_a_real_identifier("Host DB01.INTERNAL was targeted", {"db01.internal"})

    def test_false_when_no_identifier_present(self):
        assert not mentions_a_real_identifier("Suspicious activity detected", {"198.51.100.1"})


class TestEvaluateGrounding:
    def test_grounded_incident_summary_is_counted(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
        results = [
            _result(
                AnalysisTaskType.INCIDENT_SUMMARY,
                {"summary": "Attack from 198.51.100.1.", "key_points": []},
            )
        ]
        report = evaluate_grounding(incident, results, mitre_rollup=[])
        assert report.text_outputs_checked == 1
        assert report.text_outputs_grounded == 1
        assert report.ungrounded_examples == []

    def test_ungrounded_incident_summary_is_recorded(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
        results = [
            _result(
                AnalysisTaskType.INCIDENT_SUMMARY,
                {"summary": "Suspicious activity.", "key_points": []},
            )
        ]
        report = evaluate_grounding(incident, results, mitre_rollup=[])
        assert report.text_outputs_checked == 1
        assert report.text_outputs_grounded == 0
        assert report.ungrounded_examples == ["Suspicious activity."]

    def test_attack_classification_rationale_is_checked(self, db_session, brute_force_events):
        # The exact field that produced the real, confirmed hallucination
        # this project's own Phase 12 evaluation found.
        incident = _make_incident(db_session, brute_force_events)
        grounded = _result(
            AnalysisTaskType.ATTACK_CLASSIFICATION,
            {
                "category": "credential access",
                "kill_chain_stage": "initial access",
                "rationale": "Repeated failures from 198.51.100.1.",
            },
        )
        ungrounded = _result(
            AnalysisTaskType.ATTACK_CLASSIFICATION,
            {
                "category": "ransomware",
                "kill_chain_stage": "actions on objectives",
                "rationale": "Encryption activity detected.",
            },
        )
        report = evaluate_grounding(incident, [grounded, ungrounded], mitre_rollup=[])
        assert report.text_outputs_checked == 2
        assert report.text_outputs_grounded == 1
        assert report.ungrounded_examples == ["Encryption activity detected."]

    def test_each_hypothesis_is_checked_individually(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
        results = [
            _result(
                AnalysisTaskType.INVESTIGATION_HYPOTHESIS,
                {
                    "hypotheses": [
                        "Brute force from 198.51.100.1",
                        "An unrelated, unsupported guess",
                    ]
                },
            )
        ]
        report = evaluate_grounding(incident, results, mitre_rollup=[])
        assert report.text_outputs_checked == 2
        assert report.text_outputs_grounded == 1

    def test_invalid_or_empty_results_are_skipped(self, db_session, brute_force_events):
        incident = _make_incident(db_session, brute_force_events)
        invalid = _result(AnalysisTaskType.INCIDENT_SUMMARY, {"summary": "x", "key_points": []})
        invalid.validation_status = AnalysisValidationStatus.INVALID
        no_output = _result(AnalysisTaskType.INCIDENT_SUMMARY, {"summary": "x", "key_points": []})
        no_output.parsed_output = None
        report = evaluate_grounding(incident, [invalid, no_output], mitre_rollup=[])
        assert report.text_outputs_checked == 0
