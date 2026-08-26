import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.base import CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.user import User


class AuditLogEntry(UUIDPKMixin, CreatedAtMixin, Base):
    """One record of "who did what" for every mutating, non-ingestion
    action — post-roadmap addition alongside `User`/`AuthToken`, resolving
    WHATNEXT.md's "nothing tracks who triggered a pipeline run or changed
    an alert's status" gap for the actions that actually exist today
    (pipeline runs, analysis feedback). `user_id` is nullable, not because
    an action can be un-attributed by design, but because auth itself is
    still opt-in (no `User` rows configured = disabled, matching Phase
    14's original "zero-friction quick-start" promise) — a null here is
    an honest "this happened while auth was off," not a bug.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_action_created_at", "action", "created_at"),)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)

    user: Mapped["User | None"] = relationship()
