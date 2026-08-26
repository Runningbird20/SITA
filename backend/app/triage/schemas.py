"""Structured output contracts for the six Phase 7 triage tasks — the
`response_schema` each task hands to `LLMProvider.generate()`. See DEF.md
§ Phase 7.

Every schema (including nested ones) forbids unknown fields — DEF.md
§ Phase 14: schema conformance is a security boundary here, not just a
correctness check, so a response carrying fields outside the declared
contract is INVALID, not silently trimmed.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class _StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IncidentSummaryOutput(_StrictOutput):
    summary: str
    key_points: list[str]


class SeverityExplanationOutput(_StrictOutput):
    explanation: str


class AttackClassificationOutput(_StrictOutput):
    category: str
    kill_chain_stage: str
    rationale: str


class InvestigationHypothesisOutput(_StrictOutput):
    hypotheses: list[str]


class InvestigationStep(_StrictOutput):
    text: str
    priority: Literal["low", "medium", "high"]


class InvestigationStepsOutput(_StrictOutput):
    steps: list[InvestigationStep]


class MitreTechniqueSuggestion(_StrictOutput):
    technique_id: str
    technique_name: str
    rationale: str


class MitreSuggestionOutput(_StrictOutput):
    techniques: list[MitreTechniqueSuggestion]
