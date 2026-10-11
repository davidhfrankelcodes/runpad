import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampedModel
from app.models.user import User


class UserSession(TimestampedModel):
    """A logged-in browser. Only a hash of the cookie token is stored."""

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    user: Mapped[User] = relationship(lazy="joined")
