import enum

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class Role(enum.StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


class User(TimestampedModel):
    __tablename__ = "users"

    # Stored lowercase; usernames are case-insensitive.
    username: Mapped[str] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    # Users are deactivated, never deleted, so Runs keep their attribution.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
