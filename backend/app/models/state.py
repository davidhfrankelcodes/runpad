import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class StateTone(enum.StrEnum):
    """How a State should look: good (running, up), bad (stopped, down), neutral, or
    unknown (the last poll could not tell)."""

    GOOD = "good"
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
