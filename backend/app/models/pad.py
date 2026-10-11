import enum
import uuid

from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel, enum_check, str_enum


class Pad(TimestampedModel):
    """A page of buttons and tiles. Admins see every pad; members see pads that list them."""

    __tablename__ = "pads"

    name: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Members who can see this pad and press its buttons. Users are never deleted
    # (only deactivated), so these IDs never dangle.
    member_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(Uuid), default=list, server_default="{}"
    )


class ButtonColor(enum.StrEnum):
    SLATE = "slate"
    EMERALD = "emerald"
    SKY = "sky"
    AMBER = "amber"
    RED = "red"
    VIOLET = "violet"


class Button(TimestampedModel):
    """A tile on a pad that triggers an Action."""

    __tablename__ = "buttons"
    __table_args__ = (enum_check("color", ButtonColor),)

    pad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pads.id", ondelete="CASCADE"), index=True)
    action_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actions.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(64))
    color: Mapped[ButtonColor] = mapped_column(
        str_enum(ButtonColor), default=ButtonColor.SLATE, server_default=ButtonColor.SLATE.value
    )
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
