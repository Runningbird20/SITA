from app.models.analysis_result import AnalysisResult
from app.triage import prompts

_BLOCK = "Incident: Test Incident\nStatus: open    Deterministic severity: high"

_BUILDERS_AND_VERSIONS = [
    (prompts.build_incident_summary_prompt, prompts.PROMPT_VERSION_INCIDENT_SUMMARY),
    (prompts.build_severity_explanation_prompt, prompts.PROMPT_VERSION_SEVERITY_EXPLANATION),
    (prompts.build_attack_classification_prompt, prompts.PROMPT_VERSION_ATTACK_CLASSIFICATION),
    (
        prompts.build_investigation_hypothesis_prompt,
        prompts.PROMPT_VERSION_INVESTIGATION_HYPOTHESIS,
    ),
    (prompts.build_investigation_steps_prompt, prompts.PROMPT_VERSION_INVESTIGATION_STEPS),
    (prompts.build_mitre_suggestion_prompt, prompts.PROMPT_VERSION_MITRE_SUGGESTION),
]


class TestPromptBuilders:
    def test_every_prompt_embeds_the_context_block_and_asks_for_json(self):
        for build_prompt, _version in _BUILDERS_AND_VERSIONS:
            prompt = build_prompt(_BLOCK)
            assert _BLOCK in prompt
            assert "JSON" in prompt

    def test_prompt_versions_are_unique(self):
        versions = [version for _, version in _BUILDERS_AND_VERSIONS]
        assert len(versions) == len(set(versions))

    def test_severity_explanation_instructs_not_to_recompute(self):
        prompt = prompts.build_severity_explanation_prompt(_BLOCK)
        assert "do not recompute" in prompt.lower()

    def test_prompt_versions_fit_the_analysis_result_column(self):
        # SQLite doesn't enforce VARCHAR length, so a too-long tag only
        # fails against a real Postgres insert — assert it here instead.
        max_length = AnalysisResult.__table__.columns["prompt_version"].type.length
        for _build_prompt, version in _BUILDERS_AND_VERSIONS:
            assert len(version) <= max_length, f"{version!r} exceeds prompt_version({max_length})"
