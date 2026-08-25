import uuid

from pydantic import BaseModel

from app.models.enums import MitreMappingSource
from app.schemas.base import ORMBase


class MITRETechniqueRead(ORMBase):
    id: uuid.UUID
    technique_id: str
    name: str
    tactic: str
    description: str
    dataset_version: str


class AlertMitreMappingRead(ORMBase):
    """One (alert, technique) mapping, either rule- or LLM-sourced. See
    DEF.md § Phase 8/9.
    """

    technique: MITRETechniqueRead
    source: MitreMappingSource
    analysis_result_id: uuid.UUID | None = None


class TechniqueEvidenceOut(BaseModel):
    alert_id: uuid.UUID
    source: MitreMappingSource
    analysis_result_id: uuid.UUID | None = None
    confidence: float | None = None


class IncidentTechniqueEntryOut(BaseModel):
    """API shape of app.mitre.rollup.IncidentTechniqueEntry — `sources` is
    exposed as a sorted list since JSON has no native set type.
    """

    technique_id: str
    name: str
    tactic: str
    evidence: list[TechniqueEvidenceOut]
    sources: list[str]
