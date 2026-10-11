import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class Executor(enum.StrEnum):
    LOCAL = "local"
    SSH = "ssh"
    HTTP = "http"


class Concurrency(enum.StrEnum):
    REJECT = "reject"  # A new Run is refused while one is in progress.
    ALLOW = "allow"  # Runs may overlap.


class Action(TimestampedModel):
    """The thing that executes: an executor, a target, a command, and typed arguments."""

    __tablename__ = "actions"
    __table_args__ = (
        enum_check("executor", Executor),
        enum_check("concurrency", Concurrency),
        UniqueConstraint("feature_instance_id", "feature_key"),
    )

    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    executor: Mapped[Executor] = mapped_column(str_enum(Executor))
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("targets.id", ondelete="RESTRICT"), index=True
    )
    # Executor-specific command, validated by schemas.actions. For local and ssh:
    # {"script": "...", "env": {...}}; arguments are passed as env vars and positional parameters,
    # never interpolated into the script.
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Typed argument definitions: [{"name", "type", ...}], see schemas.actions.ArgSpec.
    args: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Secrets exposed as environment variables: [{"name": "API_TOKEN", "secret_id": "..."}].
    secret_env: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default="30")
    concurrency: Mapped[Concurrency] = mapped_column(
        str_enum(Concurrency), default=Concurrency.REJECT, server_default=Concurrency.REJECT.value
    )
    confirm: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Set when a Feature instance generated this Action. Managed Actions cannot be edited
    # or deleted directly; they change with their instance. Indexed by the unique constraint.
    feature_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("feature_instances.id", ondelete="CASCADE")
    )
    # Which of the Feature's actions this is ("start", "stop", ...), stable across rebuilds.
    feature_key: Mapped[str | None] = mapped_column(String(32))
