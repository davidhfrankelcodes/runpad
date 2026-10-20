import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class StateTone(enum.StrEnum):
    """How a State should look: good (running, up), warn (working, but needs attention
    soon, such as a filling disk), bad (stopped, down), neutral, or unknown (the last poll
    could not tell)."""

    GOOD = "good"
    WARN = "warn"
    BAD = "bad"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class State(TimestampedModel):
    """The current value of one thing a Feature instance reports, from its last poll."""

    __tablename__ = "states"
    __table_args__ = (
        enum_check("tone", StateTone),
        UniqueConstraint("feature_instance_id", "key"),
    )

    # Indexed by the unique constraint.
    feature_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feature_instances.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(64))
    tone: Mapped[StateTone] = mapped_column(str_enum(StateTone))
    detail: Mapped[str] = mapped_column(Text, default="", server_default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When value or tone last changed.
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StatePeriod(TimestampedModel):
    """A stretch of time a State kept one tone, for its tile's history. A poll with the same
    tone extends the latest period; a new tone, or a gap in polling, starts a new one."""

    __tablename__ = "state_periods"
    __table_args__ = (
        enum_check("tone", StateTone),
        Index("ix_state_periods_instance_key_ended_at", "feature_instance_id", "key", "ended_at"),
    )

    feature_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feature_instances.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(32))
    tone: Mapped[StateTone] = mapped_column(str_enum(StateTone))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The last poll that reported this tone.
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Tile(TimestampedModel):
    """A read-only tile on a pad showing one State of a Feature instance."""

    __tablename__ = "tiles"

    pad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pads.id", ondelete="CASCADE"), index=True)
    feature_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("feature_instances.id", ondelete="CASCADE"), index=True
    )
    state_key: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
