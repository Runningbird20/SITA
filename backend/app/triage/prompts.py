"""Prompt templates for the six Phase 7 triage tasks. Each builder takes
the rendered incident context block and returns a full prompt string
ending in an explicit JSON-only instruction. See DEF.md § Phase 7.

`prompt_version` is a plain string tag (Phase 6's convention) — bump it
whenever a prompt's wording changes meaningfully, so `run_triage`'s
idempotency check treats it as a new task and regenerates.
"""

PROMPT_VERSION_INCIDENT_SUMMARY = "triage-incident-summary-v1"
PROMPT_VERSION_SEVERITY_EXPLANATION = "triage-severity-explain-v1"
PROMPT_VERSION_ATTACK_CLASSIFICATION = "triage-attack-classify-v1"
PROMPT_VERSION_INVESTIGATION_HYPOTHESIS = "triage-inv-hypothesis-v1"
PROMPT_VERSION_INVESTIGATION_STEPS = "triage-investigation-steps-v1"
PROMPT_VERSION_MITRE_SUGGESTION = "triage-mitre-suggestion-v1"

# AnalysisResult.prompt_version is VARCHAR(30) (Phase 1's DEF.md schema) —
# SQLite doesn't enforce this, so a >30-char tag only fails against a real
# Postgres insert. Keep every tag at or under that length.

_DISCLAIMER = (
    "You are assisting a human security analyst. You are not the source of "
    "truth for severity or detection — deterministic rules already own "
    "those. Base your answer only on the incident data given below; do not "
    "invent hosts, users, or IOCs that aren't listed."
)


def build_incident_summary_prompt(context_block: str) -> str:
    return (
        f"{_DISCLAIMER}\n\n{context_block}\n\n"
        "Write a concise, human-readable summary of this incident for an "
        "analyst who has not yet looked at it, plus a short list of the "
        "most important standalone facts.\n\n"
        "Respond with a single JSON object of the exact shape "
        '{"summary": "<2-4 sentence summary>", "key_points": ["<fact>", ...]} '
        "and nothing else."
    )


def build_severity_explanation_prompt(context_block: str) -> str:
    return (
        f"{_DISCLAIMER}\n\n{context_block}\n\n"
        "The deterministic severity shown above was already computed by "
        "rule-based scoring — do not recompute or second-guess it. Explain "
        "in plain language, referencing the specific alerts and factors "
        "involved, why this incident landed at that severity.\n\n"
        "Respond with a single JSON object of the exact shape "
        '{"explanation": "<2-4 sentence explanation>"} and nothing else.'
    )


def build_attack_classification_prompt(context_block: str) -> str:
    return (
        f"{_DISCLAIMER}\n\n{context_block}\n\n"
        "Suggest an attack category (e.g. 'credential access', "
        "'reconnaissance', 'lateral movement') and the kill-chain stage "
        "this activity best fits, as a labeled hypothesis rather than a "
        "confirmed verdict.\n\n"
        "Respond with a single JSON object of the exact shape "
        '{"category": "<short category>", "kill_chain_stage": "<stage>", '
        '"rationale": "<1-2 sentence rationale>"} and nothing else.'
    )


def build_investigation_hypothesis_prompt(context_block: str) -> str:
    return (
        f"{_DISCLAIMER}\n\n{context_block}\n\n"
        "List 2-4 plausible, distinct explanations for the observed "
        "activity (e.g. targeted attack, compromised credential reuse, "
        "misconfigured automation, benign false positive). Each should be "
        "a standalone hypothesis, not a recommendation.\n\n"
        "Respond with a single JSON object of the exact shape "
        '{"hypotheses": ["<hypothesis>", ...]} and nothing else.'
    )


def build_investigation_steps_prompt(context_block: str) -> str:
    return (
        f"{_DISCLAIMER}\n\n{context_block}\n\n"
        "Suggest concrete next investigation steps an analyst should take "
        "for this specific incident, each with a priority. These are "
        "contextual suggestions, distinct from any generic checklist.\n\n"
        "Respond with a single JSON object of the exact shape "
        '{"steps": [{"text": "<step>", "priority": "low"|"medium"|"high"}, ...]} '
        "and nothing else."
    )


def build_mitre_suggestion_prompt(context_block: str) -> str:
    return (
        f"{_DISCLAIMER}\n\n{context_block}\n\n"
        "Suggest MITRE ATT&CK techniques that best match this incident's "
        "activity. If deterministic mappings are already listed above, you "
        "may confirm them or suggest additional ones the deterministic "
        "rules may have missed — you are a second, separately-labeled "
        "opinion, not a replacement for them.\n\n"
        "Respond with a single JSON object of the exact shape "
        '{"techniques": [{"technique_id": "<e.g. T1110.001>", '
        '"technique_name": "<name>", "rationale": "<1 sentence>"}, ...]} '
        "and nothing else."
    )
