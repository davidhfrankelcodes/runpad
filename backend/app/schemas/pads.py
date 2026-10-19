import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import ButtonColor, RunStatus
from app.schemas.actions import ArgSpec
from app.schemas.features import StateRead

PadName = Annotated[str, Field(min_length=1, max_length=64)]
Label = Annotated[str, Field(min_length=1, max_length=64)]


class PadCreate(BaseModel):
    name: PadName
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class PadUpdate(BaseModel):
    name: PadName | None = None
    member_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)


class PadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    position: int
    member_ids: list[uuid.UUID] = Field(description="Empty for members; only admins see this.")


class ItemKind(BaseModel):
    """What a button or tile is, so pads can show it: a feature ("Ping check") or a custom
    button."""

    name: str
    icon: str = Field(description="A name the frontend maps to an icon.")


class ButtonAction(BaseModel):
    """What pressing a button needs. Never includes the command or secret mappings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    args: list[ArgSpec]
    confirm: bool
    kind: ItemKind


class LastRun(BaseModel):
    """The latest Run of a button's action, shown on the button."""

    id: uuid.UUID
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None


class ButtonRead(BaseModel):
    id: uuid.UUID
    pad_id: uuid.UUID
    label: str
    color: ButtonColor
    position: int
    action: ButtonAction
    last_run: LastRun | None = Field(
        description="The latest Run of the action that you can see (admins: anyone's; "
        "members: their own). None if there is none."
    )


class TileRead(BaseModel):
    id: uuid.UUID
    pad_id: uuid.UUID
    feature_instance_id: uuid.UUID
    state_key: str
    label: str
    position: int
    kind: ItemKind
    check_interval_seconds: int | None = Field(
        description="How often the State is checked; None if the feature no longer polls."
    )
    state: StateRead | None = Field(description="None until the first poll.")


class PadDetail(PadRead):
    buttons: list[ButtonRead]
    tiles: list[TileRead]


class TileCreate(BaseModel):
    feature_instance_id: uuid.UUID
    state_key: str = Field(max_length=32)
    label: Label


class TileUpdate(BaseModel):
    pad_id: uuid.UUID | None = Field(default=None, description="Move the tile to this pad.")
    label: Label | None = None


class ButtonCreate(BaseModel):
    action_id: uuid.UUID
    label: Label
    color: ButtonColor = ButtonColor.SLATE


class ButtonUpdate(BaseModel):
    pad_id: uuid.UUID | None = Field(default=None, description="Move the button to this pad.")
    label: Label | None = None
    color: ButtonColor | None = None


class BoardItem(BaseModel):
    kind: Literal["button", "tile"]
    id: uuid.UUID


class BoardOrder(BaseModel):
    items: list[BoardItem] = Field(
        description="Every button and tile on the pad, in the new order.", max_length=1000
    )


class Order(BaseModel):
    ids: list[uuid.UUID] = Field(description="Every item, in the new order.", max_length=500)
