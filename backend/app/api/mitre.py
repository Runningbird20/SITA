import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.mitre import MITRETechnique
from app.schemas.mitre import MITRETechniqueRead
from app.schemas.pagination import Page

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/mitre-techniques", tags=["mitre"])

_SORTABLE = {
    "technique_id": MITRETechnique.technique_id,
    "name": MITRETechnique.name,
}


@router.get("", response_model=Page[MITRETechniqueRead])
def list_mitre_techniques(
    tactic: str | None = Query(None),
    sort: str | None = Query(None, description="technique_id | name"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
) -> Page[MITRETechniqueRead]:
    """List/filter the locally vendored MITRE ATT&CK technique subset."""
    stmt = select(MITRETechnique)
    if tactic is not None:
        stmt = stmt.where(MITRETechnique.tactic == tactic)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="technique_id")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/{technique_id}", response_model=MITRETechniqueRead)
def get_mitre_technique(technique_id: uuid.UUID, db: Session = Depends(get_db)) -> MITRETechnique:
    """Get one MITRE technique by its internal id."""
    technique = db.get(MITRETechnique, technique_id)
    if technique is None:
        raise NotFoundError("MITRETechnique", technique_id)
    return technique
