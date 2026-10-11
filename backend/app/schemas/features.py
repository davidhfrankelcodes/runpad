import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import StateTone

InstanceName = Annotated[str, Field(min_length=1, max_length=64)]


class FeatureRead(BaseModel):
    id: str
    name: str
    description: str
    icon: str
    category: str
    config_schema: dict[str, Any] = Field(
        description="JSON schema of the setup form. Fields with x-target-kind pick a Target."
    )


class FeatureInstanceCreate(BaseModel):
    feature_id: str
    name: InstanceName
    config: dict[str, Any]
    pad_id: uuid.UUID | None = Field(
        default=None, description="Pad to put the generated buttons on. None: no buttons."
    )


class FeatureInstanceUpdate(BaseModel):
    """Changing the config rebuilds the instance's Actions in place."""

    name: InstanceName | None = None
    config: dict[str, Any] | None = None


class TileTemplateRead(BaseModel):
    state_key: str
    label: str


class FeatureInstanceRead(BaseModel):
    id: uuid.UUID
    feature_id: str
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
