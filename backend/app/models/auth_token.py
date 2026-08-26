import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.user import User


class AuthToken(UUIDPKMixin, CreatedAtMixin, Base):
    """A live login session, issued by `POST /auth/login`. Only the SHA-256
    hash of the bearer token is stored — same principle as `User.password_hash`,
    so a DB leak alone can't hand out working credentials. Deleting the row
    (logout, or a future admin "revoke") ends the session immediately;
    unlike a JWT, nothing needs a blocklist to make revocation real.
    """

    __tablename__ = "auth_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship()
