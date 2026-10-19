import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class RunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"  # The app stopped while the Run was in progress.


class Run(TimestampedModel):
    """One execution of an Action. Append-only: rows are never deleted (this is the audit log)."""

    __tablename__ = "runs"
    __table_args__ = (
        enum_check("status", RunStatus),
        # An action's latest Run, for the last-run line on its buttons.
        Index("ix_runs_action_id_started_at", "action_id", "started_at"),
    )

    # Kept when the Action is deleted; action_name preserves what ran.
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("actions.id", ondelete="SET NULL")
    )
    action_name: Mapped[str] = mapped_column(String(64))
    # Null means the system (State polling) triggered the Run.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    args: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exit_code: Mapped[int | None] = mapped_column(Integer)
    # Merged stdout and stderr, secrets redacted, capped at runner.OUTPUT_LIMIT_BYTES.
    output: Mapped[str] = mapped_column(Text, default="", server_default="")
    output_truncated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Why the Run could not complete normally (connection failure, timeout, ...).
    error: Mapped[str | None] = mapped_column(Text)
