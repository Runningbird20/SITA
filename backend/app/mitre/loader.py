"""Loads the vendored local MITRE ATT&CK subset from data/mitre/ into the
MITRETechnique table — no runtime network dependency. See DEF.md § Phase 8.
"""

from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mitre import MITRETechnique
from app.schemas.mitre_run import MitreLoadReport

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_PATH = REPO_ROOT / "data" / "mitre" / "techniques.json"


class MitreTechniqueRecord(BaseModel):
    technique_id: str
    name: str
    tactic: str
    description: str


class MitreDataset(BaseModel):
    dataset_version: str
    techniques: list[MitreTechniqueRecord]


def load_techniques(db: Session, path: Path = DEFAULT_DATASET_PATH) -> MitreLoadReport:
    dataset = MitreDataset.model_validate_json(path.read_text())

    existing = {t.technique_id: t for t in db.scalars(select(MITRETechnique)).all()}

    created = 0
    updated = 0
    for record in dataset.techniques:
        technique = existing.get(record.technique_id)
        if technique is None:
            db.add(
                MITRETechnique(
                    technique_id=record.technique_id,
                    name=record.name,
                    tactic=record.tactic,
                    description=record.description,
                    dataset_version=dataset.dataset_version,
                )
            )
            created += 1
            continue

        changed = (
            technique.name != record.name
            or technique.tactic != record.tactic
            or technique.description != record.description
            or technique.dataset_version != dataset.dataset_version
        )
        if changed:
            technique.name = record.name
            technique.tactic = record.tactic
            technique.description = record.description
            technique.dataset_version = dataset.dataset_version
            updated += 1

    db.flush()

    return MitreLoadReport(
        dataset_version=dataset.dataset_version,
        techniques_created=created,
        techniques_updated=updated,
    )
