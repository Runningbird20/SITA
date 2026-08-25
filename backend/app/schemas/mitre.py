import uuid

from app.schemas.base import ORMBase


class MITRETechniqueRead(ORMBase):
    id: uuid.UUID
    technique_id: str
    name: str
    tactic: str
    description: str
    dataset_version: str
