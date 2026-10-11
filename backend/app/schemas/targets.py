import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

from app.executors.ssh import SshKeyError, parse_host_key

TargetName = Annotated[str, Field(min_length=1, max_length=64)]
Host = Annotated[str, Field(min_length=1, max_length=253, pattern=r"^[A-Za-z0-9.:\-]+$")]
Port = Annotated[int, Field(ge=1, le=65535)]


class HostKeyScanRequest(BaseModel):
    host: Host
    port: Port = 22


class HostKeyRead(BaseModel):
    public_key: str
    algorithm: str
    fingerprint: str


class SshConfig(BaseModel):
    host: Host
    port: Port = 22
    username: Annotated[
        str, Field(min_length=1, max_length=32, pattern=r"^[A-Za-z_][A-Za-z0-9_.-]*\$?$")
    ]
    host_key: str = Field(
        description="The pinned host key from /targets/scan-host-key, as one OpenSSH line."
    )

    @field_validator("host_key")
    @classmethod
    def _valid_host_key(cls, value: str) -> str:
        try:
            return parse_host_key(value).public_key
        except SshKeyError as exc:
            raise ValueError(str(exc)) from exc


class SshConfigRead(SshConfig):
    host_key_fingerprint: str


class HttpConfig(BaseModel):
    base_url: AnyHttpUrl
    verify_tls: bool = Field(
        default=True, description="Turn off only for self-signed certificates."
    )


class SshTargetCreate(BaseModel):
    kind: Literal["ssh"]
    name: TargetName
    secret_id: uuid.UUID = Field(description="An ssh_key secret used to log in.")
    config: SshConfig


class HttpTargetCreate(BaseModel):
    kind: Literal["http"]
    name: TargetName
    secret_id: uuid.UUID | None = Field(
        default=None, description="Optional text secret sent as a bearer token."
    )
    config: HttpConfig


TargetCreate = Annotated[SshTargetCreate | HttpTargetCreate, Field(discriminator="kind")]


class TargetUpdate(BaseModel):
    """Fields to change. `config` replaces the whole config and must match the target's kind."""

    name: TargetName | None = None
    secret_id: uuid.UUID | None = None
    clear_secret: bool = Field(default=False, description="HTTP only: remove the bearer token.")
    config: SshConfig | HttpConfig | None = None


class TargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    kind: Literal["ssh", "http"]
    secret_id: uuid.UUID | None
    config: SshConfigRead | HttpConfig
    created_at: datetime
    updated_at: datetime


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
