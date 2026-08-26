import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import PageParams, apply_sort, pagination_params
from app.auth.deps import CurrentUser, require_admin
from app.core.config import get_settings
from app.db.session import get_db
from app.models.audit_log import AuditLogEntry
from app.schemas.audit_log import AuditLogEntryRead
from app.schemas.pagination import Page

router = APIRouter(prefix=f"{get_settings().api_v1_prefix}/audit-log", tags=["audit-log"])

_SORTABLE = {"created_at": AuditLogEntry.created_at}


@router.get("", response_model=Page[AuditLogEntryRead])
def list_audit_log(
    user_id: uuid.UUID | None = Query(None),
    action: str | None = Query(None),
    sort: str | None = Query(None, description="created_at"),
    page: PageParams = Depends(pagination_params),
    db: Session = Depends(get_db),
    _admin: CurrentUser | None = Depends(require_admin),
) -> Page[AuditLogEntryRead]:
    """Admin-only — the read side of app/core/audit.py::record_audit,
    otherwise the audit trail would be write-only and useless to anyone
    but a direct DB query.
    """
    stmt = select(AuditLogEntry)
    if user_id is not None:
        stmt = stmt.where(AuditLogEntry.user_id == user_id)
    if action is not None:
        stmt = stmt.where(AuditLogEntry.action == action)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = apply_sort(stmt, sort, _SORTABLE, default="-created_at")
    items = db.scalars(stmt.limit(page.limit).offset(page.offset)).all()
    return Page(items=items, total=total, limit=page.limit, offset=page.offset)
