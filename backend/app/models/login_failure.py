from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class LoginFailure(TimestampedModel):
    """One failed login, kept for login_limits.WINDOW to rate-limit password guessing."""

    __tablename__ = "login_failures"
    __table_args__ = (
        Index("ix_login_failures_ip_created_at", "ip", "created_at"),
        Index("ix_login_failures_username_created_at", "username", "created_at"),
    )

    # As typed (lowercased, truncated); it may not be a real user.
    username: Mapped[str] = mapped_column(String(32))
    ip: Mapped[str] = mapped_column(String(45))
