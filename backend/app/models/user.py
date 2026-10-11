import enum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class Role(enum.StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class User(TimestampedModel):
    __tablename__ = "users"
    __table_args__ = (enum_check("role", Role),)

    # Stored lowercase; usernames are case-insensitive.
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(str_enum(Role))
    # Users are deactivated, never deleted, so Runs keep their attribution.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # The user's theme.park theme ("theme-options/nord", "community-theme-options/..."),
    # or None for runpad's own colors.
    theme: Mapped[str | None] = mapped_column(String(100))
