import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import SecretKind

SecretName = Annotated[str, Field(min_length=1, max_length=64)]
Description = Annotated[str, Field(max_length=500)]
SecretValue = Annotated[str, Field(min_length=1, max_length=16_384)]


class SecretRead(BaseModel):
    """A secret's metadata. The value is write-only and never returned."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: SecretKind
    description: str
    public_key: str | None = Field(
        description="For ssh_key secrets: add this line to the host's authorized_keys."
    )
    created_at: datetime
    updated_at: datetime


class SecretCreate(BaseModel):
    name: SecretName
    kind: SecretKind
    description: Description = ""
    value: SecretValue = Field(description="Plain text, or an unencrypted OpenSSH/PEM private key.")


class SshKeyGenerate(BaseModel):
    name: SecretName
    description: Description = ""


class SecretUpdate(BaseModel):
    name: SecretName | None = None
    description: Description | None = None
    value: SecretValue | None = Field(default=None, description="Replace the stored value.")
