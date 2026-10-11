import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import StateTone

InstanceName = Annotated[str, Field(min_length=1, max_length=64)]


class CatalogItemRead(BaseModel):
    key: str
    kind: Literal["button", "tile"]
    name: str
    description: str


class FeatureRead(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    items: list[CatalogItemRead] = Field(
        description="What can be added: each item is one button or one tile."
    )
    config_schema: dict[str, Any] = Field(
        description="JSON schema of the setup form. Fields with x-target-kind pick a Target."
    )


class FeatureInstanceCreate(BaseModel):
    feature_id: str
    item: str = Field(description="The key of one of the feature's items.")
    name: InstanceName | None = Field(
        default=None, description="Defaults to what it adds, such as 'Start plex'."
    )
    config: dict[str, Any]
    pad_id: uuid.UUID | None = Field(
        default=None,
        description="Pad to put the button or tile on. Required for a tile; without one, "
        "a button item only creates its action.",
    )


class FeatureInstanceUpdate(BaseModel):
    """Changing the config rebuilds the instance's Action in place. The item cannot change."""

    name: InstanceName | None = None
    config: dict[str, Any] | None = None


class TileTemplateRead(BaseModel):
    state_key: str
    label: str


class FeatureInstanceRead(BaseModel):
    id: uuid.UUID
    feature_id: str
    item: str
    name: str
    config: dict[str, Any]
    tiles: list[TileTemplateRead] = Field(description="Tiles this instance can put on a pad.")
    created_at: datetime
    updated_at: datetime


class StateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature_instance_id: uuid.UUID
    key: str
    value: str
    tone: StateTone
    detail: str
    checked_at: datetime
    changed_at: datetime
