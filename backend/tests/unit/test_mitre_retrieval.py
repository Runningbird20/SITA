import uuid
from datetime import UTC, datetime

from app.mitre.retrieval import candidate_techniques_for_incident
from app.models.mitre import MITRETechnique
from app.triage.context import AlertContext, IncidentContext

NOW = datetime(2026, 1, 15, 3, 0, 0, tzinfo=UTC)


def _technique(db_session, technique_id, name, tactic, description="") -> MITRETechnique:
    technique = MITRETechnique(
        technique_id=technique_id,
        name=name,
        tactic=tactic,
        description=description,
        dataset_version="test-v1",
    )
    db_session.add(technique)
    db_session.flush()
    return technique


def _ctx(rule_mitre_techniques, alerts=None, ioc_summaries=None, title="Test Incident"):
    return IncidentContext(
        incident_id=uuid.uuid4(),
        title=title,
        status="open",
        severity="high",
        first_activity_at=NOW,
        last_activity_at=NOW,
        alerts=alerts or [],
        ioc_summaries=ioc_summaries or [],
        rule_mitre_techniques=rule_mitre_techniques,
    )


def _alert(rationale, detection_name="Test Detection", category="network"):
    return AlertContext(
        alert_id=uuid.uuid4(),
        detection_name=detection_name,
        category=category,
        severity="high",
        confidence=0.8,
        rationale=rationale,
        first_event_at=NOW,
        last_event_at=NOW,
    )


class TestCandidateTechniquesForIncident:
    def test_only_shares_tactics_with_rule_mapped_techniques(self, db_session):
        _technique(db_session, "T1110", "Brute Force", "credential-access")
        _technique(db_session, "T1110.003", "Password Spraying", "credential-access")
        _technique(db_session, "T1046", "Network Service Discovery", "discovery")

        ctx = _ctx(rule_mitre_techniques=["T1110"])
        candidates = candidate_techniques_for_incident(db_session, ctx)

        ids = {c.technique_id for c in candidates}
        assert ids == {"T1110.003"}

    def test_excludes_already_rule_mapped_technique_ids(self, db_session):
        _technique(db_session, "T1110", "Brute Force", "credential-access")
        _technique(db_session, "T1110.003", "Password Spraying", "credential-access")

        ctx = _ctx(rule_mitre_techniques=["T1110", "T1110.003"])
        candidates = candidate_techniques_for_incident(db_session, ctx)

        assert candidates == []

    def test_no_rule_mapped_techniques_falls_back_to_the_full_pool(self, db_session):
        _technique(db_session, "T1110", "Brute Force", "credential-access")
        _technique(db_session, "T1046", "Network Service Discovery", "discovery")

        ctx = _ctx(rule_mitre_techniques=[])
        candidates = candidate_techniques_for_incident(db_session, ctx)

        assert {c.technique_id for c in candidates} == {"T1110", "T1046"}

    def test_keyword_overlap_ranks_more_relevant_candidates_first(self, db_session):
        _technique(
            db_session,
            "T1046",
            "Network Service Discovery",
            "discovery",
            "Adversaries scan ports to discover services running on remote hosts.",
        )
        _technique(
            db_session,
            "T1018",
            "Remote System Discovery",
            "discovery",
            "Adversaries list other systems on a network by hostname.",
        )
        ctx = _ctx(
            rule_mitre_techniques=[],
            alerts=[_alert("198.51.100.9 touched 15 distinct ports scanning for open services")],
        )

        candidates = candidate_techniques_for_incident(db_session, ctx)

        assert candidates[0].technique_id == "T1046"

    def test_limit_bounds_the_returned_candidate_count(self, db_session):
        for i in range(20):
            _technique(db_session, f"T9{i:03d}", f"Technique {i}", "discovery")

        ctx = _ctx(rule_mitre_techniques=[])
        candidates = candidate_techniques_for_incident(db_session, ctx, limit=5)

        assert len(candidates) == 5

    def test_no_techniques_in_the_dataset_returns_an_empty_list(self, db_session):
        ctx = _ctx(rule_mitre_techniques=[])
        assert candidate_techniques_for_incident(db_session, ctx) == []
