import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import Role

Username = Annotated[
    str,
    AfterValidator(str.lower),
    Field(
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9_.-]+$",
        description="Letters, digits, '.', '_' or '-'. Case-insensitive.",
    ),
]
# Upper bound keeps argon2 hashing cost bounded.
Password = Annotated[str, Field(min_length=12, max_length=256)]


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: Role
    is_active: bool
    created_at: datetime


class SetupStatus(BaseModel):
    required: bool


class SetupRequest(BaseModel):
    username: Username
    password: Password


class LoginRequest(BaseModel):
    username: Annotated[str, Field(max_length=32)]
    password: Annotated[str, Field(max_length=256)]


class PasswordChange(BaseModel):
    current_password: Annotated[str, Field(max_length=256)]
    new_password: Password


class UserCreate(BaseModel):
    username: Username
    password: Password
    role: Role = Role.MEMBER


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None
    password: Password | None = None
