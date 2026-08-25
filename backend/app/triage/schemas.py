"""Structured output contracts for the six Phase 7 triage tasks — the
`response_schema` each task hands to `LLMProvider.generate()`. See DEF.md
§ Phase 7.
"""

from typing import Literal

from pydantic import BaseModel


class IncidentSummaryOutput(BaseModel):
    summary: str
    key_points: list[str]


class SeverityExplanationOutput(BaseModel):
    explanation: str


class AttackClassificationOutput(BaseModel):
    category: str
    kill_chain_stage: str
    rationale: str


class InvestigationHypothesisOutput(BaseModel):
    hypotheses: list[str]


class InvestigationStep(BaseModel):
    text: str
    priority: Literal["low", "medium", "high"]


class InvestigationStepsOutput(BaseModel):
    steps: list[InvestigationStep]


class MitreTechniqueSuggestion(BaseModel):
    technique_id: str
    technique_name: str
    rationale: str


class MitreSuggestionOutput(BaseModel):
    techniques: list[MitreTechniqueSuggestion]
