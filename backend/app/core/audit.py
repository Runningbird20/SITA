"""Records "who did what" for mutating, non-ingestion actions. See DEF.md
§ Phase 14, "Multi-user / RBAC (post-roadmap)".
"""

import uuid

from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser
from app.models.audit_log import AuditLogEntry


def record_audit(
    db: Session,
    current_user: CurrentUser | None,
    action: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    detail: dict | None = None,
) -> None:
    """current_user is None exactly when auth is disabled — still logged,
    with a null user_id, rather than silently skipped. See
    AuditLogEntry's own docstring for why that's not treated as a bug.
    """
    db.add(
        AuditLogEntry(
            user_id=current_user.id if current_user is not None else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
        )
    )
