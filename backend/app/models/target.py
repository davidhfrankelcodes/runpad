import enum
import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class TargetKind(enum.StrEnum):
    SSH = "ssh"
    HTTP = "http"


class Target(TimestampedModel):
    """Where an Action runs: an SSH host or an HTTP endpoint."""

    __tablename__ = "targets"
    __table_args__ = (enum_check("kind", TargetKind),)

    name: Mapped[str] = mapped_column(String(64), unique=True)
    kind: Mapped[TargetKind] = mapped_column(str_enum(TargetKind))
    # SSH: the private key (required). HTTP: an optional bearer token.
    secret_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("secrets.id", ondelete="RESTRICT"), index=True
    )
    # Kind-specific settings, validated by schemas.targets.SshConfig / HttpConfig.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
