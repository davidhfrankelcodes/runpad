import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

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


class FeatureInstanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    feature_id: str
    name: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
