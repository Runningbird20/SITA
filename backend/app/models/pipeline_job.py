import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.types import JSONVariant
from app.models.base import CreatedAtMixin, UUIDPKMixin
from app.models.enums import PipelineJobStatus, PipelineJobType, PipelineStage

if TYPE_CHECKING:
    from app.models.user import User


class PipelineJob(UUIDPKMixin, CreatedAtMixin, Base):
    """Tracks one background execution of POST /pipeline/run or
    /pipeline/reanalyze — resolves WHATNEXT.md's "Background job execution
    for triage" item. See DEF.md § Phase 9, "Post-roadmap addition:
    background pipeline jobs".

    Persisted (not in-memory) specifically so a status-poll request can
    land on a different worker process than the one executing the job —
    matters under docker-compose.prod.yml's multi-worker backend, where an
    in-memory dict keyed by job_id would only be visible to whichever
    worker happened to receive that particular poll request.
    """

    __tablename__ = "pipeline_jobs"
    __table_args__ = (Index("ix_pipeline_jobs_status_created_at", "status", "created_at"),)

    job_type: Mapped[PipelineJobType] = mapped_column(String(30), nullable=False)
    status: Mapped[PipelineJobStatus] = mapped_column(
        String(20), nullable=False, default=PipelineJobStatus.PENDING
    )
    since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_stage: Mapped[PipelineStage | None] = mapped_column(String(20), nullable=True)
    progress_current: Mapped[int | None] = mapped_column(nullable=True)
    progress_total: Mapped[int | None] = mapped_column(nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONVariant, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped["User | None"] = relationship()
