import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The choices offered for a new token's lifetime; None means it never expires.
ExpiryDays = Literal[7, 30, 90, 365]


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64, description="What the token is for.")
    expires_in_days: ExpiryDays | None = Field(
        default=30, description="7, 30, 90, or 365 days; null for a token that never expires."
    )


class ApiTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    prefix: str = Field(description="The start of the token, to tell tokens apart.")
    created_at: datetime
    expires_at: datetime | None = Field(description="None: never expires.")
    last_used_at: datetime | None


class ApiTokenCreated(ApiTokenRead):
    token: str = Field(
        description="Send as `Authorization: Bearer <token>`. Shown only once; runpad keeps "
        "only a hash."
    )
