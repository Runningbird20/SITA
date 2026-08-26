from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import CreatedAtMixin, UUIDPKMixin
from app.models.enums import UserRole


class User(UUIDPKMixin, CreatedAtMixin, Base):
    """A named analyst/admin account — post-roadmap addition replacing the
    single shared bearer token (`[[dashboard-auth]]`, Phase 14) so mutating
    actions are attributable to a real person, not just "someone with the
    token." See DEF.md § Phase 14, "Multi-user / RBAC (post-roadmap)".
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), nullable=False)
