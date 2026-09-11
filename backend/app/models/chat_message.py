import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import CreatedAtMixin, UUIDPKMixin
from app.models.enums import AnalysisValidationStatus, ChatRole

if TYPE_CHECKING:
    from app.models.incident import Incident


class ChatMessage(UUIDPKMixin, CreatedAtMixin, Base):
    """One turn in a conversational Q&A thread scoped to one Incident —
    resolves WHATNEXT.md's "Bigger bets" item, "a conversational interface
    with an incident". See DEF.md § Phase 7, "Post-roadmap addition: a
    conversational interface with an incident".

    Deliberately a separate table from AnalysisResult rather than reusing
    it with task_type=chat_response: AnalysisResult is one row per fixed
    task per incident (six of them, each re-run replaces nothing, kept for
    auditability); a chat thread is an open-ended, ordered sequence with
    two authors (the analyst's own question is a row here too, not just
    the model's answer), which is a genuinely different shape.

    provider/model/prompt_version/validation_status/confidence/latency_ms
    are only ever populated for role=assistant rows — an analyst's own
    question has no such provenance to record, so they stay NULL for
    role=user rows rather than being filled with placeholder values.
    """

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_incident_id_created_at", "incident_id", "created_at"),
    )

    incident_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("incidents.id"), nullable=False, index=True
    )
    role: Mapped[ChatRole] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(30), nullable=True)
    validation_status: Mapped[AnalysisValidationStatus | None] = mapped_column(
        String(20), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    incident: Mapped["Incident"] = relationship(back_populates="chat_messages")
