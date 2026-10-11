import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import ButtonColor
from app.schemas.actions import ArgSpec

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


class ButtonAction(BaseModel):
    """What pressing a button needs. Never includes the command or secret mappings."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    args: list[ArgSpec]
    confirm: bool


class ButtonRead(BaseModel):
    id: uuid.UUID
    pad_id: uuid.UUID
    label: str
    color: ButtonColor
    position: int
    action: ButtonAction


class PadDetail(PadRead):
    buttons: list[ButtonRead]


class ButtonCreate(BaseModel):
    action_id: uuid.UUID
    label: Label
    color: ButtonColor = ButtonColor.SLATE


class ButtonUpdate(BaseModel):
    pad_id: uuid.UUID | None = Field(default=None, description="Move the button to this pad.")
    label: Label | None = None
    color: ButtonColor | None = None


class Order(BaseModel):
    ids: list[uuid.UUID] = Field(description="Every item, in the new order.", max_length=500)
