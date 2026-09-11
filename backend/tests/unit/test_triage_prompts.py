from app.mitre.retrieval import CandidateTechnique
from app.models.analysis_result import AnalysisResult
from app.models.chat_message import ChatMessage
from app.models.enums import ChatRole
from app.triage import prompts

_BLOCK = "Incident: Test Incident\nStatus: open    Deterministic severity: high"

# build_mitre_suggestion_prompt takes an extra `candidates` argument (see
# DEF.md § Phase 8 "Post-roadmap addition: candidate-technique retrieval")
# so it doesn't share the other five builders' uniform Callable[[str], str]
# shape — tested separately below, but still included in the
# version-uniqueness and column-length checks since those apply regardless
# of signature.
_BUILDERS_AND_VERSIONS = [
    (prompts.build_incident_summary_prompt, prompts.PROMPT_VERSION_INCIDENT_SUMMARY),
    (prompts.build_severity_explanation_prompt, prompts.PROMPT_VERSION_SEVERITY_EXPLANATION),
    (prompts.build_attack_classification_prompt, prompts.PROMPT_VERSION_ATTACK_CLASSIFICATION),
    (
        prompts.build_investigation_hypothesis_prompt,
        prompts.PROMPT_VERSION_INVESTIGATION_HYPOTHESIS,
    ),
    (prompts.build_investigation_steps_prompt, prompts.PROMPT_VERSION_INVESTIGATION_STEPS),
]

_ALL_PROMPT_VERSIONS = [version for _, version in _BUILDERS_AND_VERSIONS] + [
    prompts.PROMPT_VERSION_MITRE_SUGGESTION,
    prompts.PROMPT_VERSION_CHAT,
]

_SAMPLE_CANDIDATES = [
    CandidateTechnique(
        technique_id="T1018",
        name="Remote System Discovery",
        tactic="discovery",
        description="Adversaries may attempt to get a listing of other systems.",
    )
]


class TestPromptBuilders:
    def test_every_prompt_embeds_the_context_block_and_asks_for_json(self):
        for build_prompt, _version in _BUILDERS_AND_VERSIONS:
            prompt = build_prompt(_BLOCK)
            assert _BLOCK in prompt
            assert "JSON" in prompt

    def test_prompt_versions_are_unique(self):
        assert len(_ALL_PROMPT_VERSIONS) == len(set(_ALL_PROMPT_VERSIONS))

    def test_severity_explanation_instructs_not_to_recompute(self):
        prompt = prompts.build_severity_explanation_prompt(_BLOCK)
        assert "do not recompute" in prompt.lower()

    def test_prompt_versions_fit_the_analysis_result_column(self):
        # SQLite doesn't enforce VARCHAR length, so a too-long tag only
        # fails against a real Postgres insert — assert it here instead.
        max_length = AnalysisResult.__table__.columns["prompt_version"].type.length
        for version in _ALL_PROMPT_VERSIONS:
            assert len(version) <= max_length, f"{version!r} exceeds prompt_version({max_length})"


class TestMitreSuggestionPrompt:
    def test_embeds_context_block_and_asks_for_json(self):
        prompt = prompts.build_mitre_suggestion_prompt(_BLOCK, _SAMPLE_CANDIDATES)
        assert _BLOCK in prompt
        assert "JSON" in prompt

    def test_lists_candidate_techniques_by_id_and_name(self):
        prompt = prompts.build_mitre_suggestion_prompt(_BLOCK, _SAMPLE_CANDIDATES)
        assert "T1018" in prompt
        assert "Remote System Discovery" in prompt

    def test_instructs_grounding_in_candidates_not_free_recall(self):
        prompt = prompts.build_mitre_suggestion_prompt(_BLOCK, _SAMPLE_CANDIDATES)
        assert "do not invent a technique_id" in prompt

    def test_empty_candidate_list_still_produces_a_valid_prompt(self):
        prompt = prompts.build_mitre_suggestion_prompt(_BLOCK, [])
        assert _BLOCK in prompt
        assert "none found" in prompt.lower()

    def test_truncates_a_long_candidate_description(self):
        long_description = "x" * 500
        candidates = [
            CandidateTechnique(
                technique_id="T1018",
                name="Remote System Discovery",
                tactic="discovery",
                description=long_description,
            )
        ]
        prompt = prompts.build_mitre_suggestion_prompt(_BLOCK, candidates)
        assert long_description not in prompt
        assert "x" * 180 in prompt


class TestChatPrompt:
    def test_embeds_context_block_history_and_question_and_asks_for_json(self):
        prompt = prompts.build_chat_prompt(_BLOCK, [], "What happened here?")
        assert _BLOCK in prompt
        assert "What happened here?" in prompt
        assert "JSON" in prompt

    def test_no_prior_history_says_so_explicitly(self):
        prompt = prompts.build_chat_prompt(_BLOCK, [], "Anything else?")
        assert "no prior questions" in prompt.lower()

    def test_prior_turns_are_rendered_in_order(self):
        history = [
            (ChatRole.USER, "Is this a brute force attempt?"),
            (ChatRole.ASSISTANT, "Yes, based on the repeated failed logins."),
        ]
        prompt = prompts.build_chat_prompt(_BLOCK, history, "From which IP?")
        assert "Is this a brute force attempt?" in prompt
        assert "Yes, based on the repeated failed logins." in prompt
        assert prompt.index("Is this a brute force attempt?") < prompt.index(
            "Yes, based on the repeated failed logins."
        )

    def test_prompt_version_fits_the_chat_message_column(self):
        max_length = ChatMessage.__table__.columns["prompt_version"].type.length
        assert len(prompts.PROMPT_VERSION_CHAT) <= max_length
