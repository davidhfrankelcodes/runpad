import re
import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Concurrency

ArgName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")]
Label = Annotated[str, Field(max_length=64)]
# Arguments reach commands as environment variables, which cannot contain NUL.
NO_NUL = re.compile(r"\x00")


class _ArgBase(BaseModel):
    name: ArgName = Field(description="Available to the script as $ARG_<NAME> (upper-cased).")
    label: Label = ""

    def check_value(self, value: object) -> str | int | bool:
        raise NotImplementedError


class StringArg(_ArgBase):
    type: Literal["string"]
    pattern: str = Field(
        min_length=1,
        max_length=500,
        description="The whole value must match this regular expression.",
    )
    max_length: int = Field(default=200, ge=1, le=1000)
    default: str | None = Field(default=None, description="No default means required.")

    @field_validator("pattern")
    @classmethod
    def _compiles(cls, pattern: str) -> str:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
        return pattern

    @model_validator(mode="after")
    def _default_is_valid(self) -> Self:
        if self.default is not None:
            self.check_value(self.default)
        return self

    def check_value(self, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("must be a string")
        if len(value) > self.max_length:
            raise ValueError(f"must be at most {self.max_length} characters")
        if NO_NUL.search(value) or not re.fullmatch(self.pattern, value):
            raise ValueError(f"must match {self.pattern}")
        return value


class IntegerArg(_ArgBase):
    type: Literal["integer"]
    min: int
    max: int
    default: int | None = None

    @model_validator(mode="after")
    def _bounds(self) -> Self:
        if self.min > self.max:
            raise ValueError("min must not exceed max")
        if self.default is not None:
            self.check_value(self.default)
        return self

    def check_value(self, value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("must be an integer")
        if not self.min <= value <= self.max:
            raise ValueError(f"must be between {self.min} and {self.max}")
        return value


class EnumArg(_ArgBase):
    type: Literal["enum"]
    choices: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        min_length=1, max_length=50
    )
    default: str | None = None

    @model_validator(mode="after")
    def _choices(self) -> Self:
        if len(set(self.choices)) != len(self.choices):
            raise ValueError("choices must be unique")
        if any(NO_NUL.search(c) for c in self.choices):
            raise ValueError("choices must not contain NUL")
        if self.default is not None:
            self.check_value(self.default)
        return self

    def check_value(self, value: object) -> str:
        if value not in self.choices:
            raise ValueError(f"must be one of: {', '.join(self.choices)}")
        return str(value)


class BooleanArg(_ArgBase):
    type: Literal["boolean"]
    default: bool = False

    def check_value(self, value: object) -> bool:
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value


ArgSpec = Annotated[StringArg | IntegerArg | EnumArg | BooleanArg, Field(discriminator="type")]

RESERVED_ENV = frozenset({"PATH", "HOME", "LANG", "LC_ALL", "SHELL", "USER", "PWD", "IFS"})


class SecretEnv(BaseModel):
    name: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
    secret_id: uuid.UUID

    @field_validator("name")
    @classmethod
    def _not_reserved(cls, name: str) -> str:
        if name in RESERVED_ENV or name.startswith(("ARG_", "RUNPAD_")):
            raise ValueError(f"{name} is reserved")
        return name


class ScriptSpec(BaseModel):
    script: str = Field(
        min_length=1,
        max_length=65_536,
        description="Run with /bin/sh -c. Arguments arrive as $ARG_<NAME> and as $1, $2, ... "
        "in the order they are defined; they are never interpolated into this text.",
    )


def _unique_names(items: list[ArgSpec] | list[SecretEnv], what: str) -> None:
    names = [item.name for item in items]
    if len(set(names)) != len(names):
        raise ValueError(f"{what} names must be unique")


ActionName = Annotated[str, Field(min_length=1, max_length=64)]
Description = Annotated[str, Field(max_length=500)]
Timeout = Annotated[int, Field(ge=1, le=3600)]


class ActionCreate(BaseModel):
    name: ActionName
    description: Description = ""
    executor: Literal["local"]
    spec: ScriptSpec
    args: list[ArgSpec] = Field(default_factory=list, max_length=20)
    secret_env: list[SecretEnv] = Field(default_factory=list, max_length=20)
    timeout_seconds: Timeout = 30
    concurrency: Concurrency = Concurrency.REJECT
    confirm: bool = Field(default=False, description="Ask for confirmation before running.")

    @model_validator(mode="after")
    def _unique(self) -> Self:
        _unique_names(self.args, "Argument")
        _unique_names(self.secret_env, "Secret variable")
        return self


class ActionUpdate(BaseModel):
    name: ActionName | None = None
    description: Description | None = None
    spec: ScriptSpec | None = None
    args: list[ArgSpec] | None = Field(default=None, max_length=20)
    secret_env: list[SecretEnv] | None = Field(default=None, max_length=20)
    timeout_seconds: Timeout | None = None
    concurrency: Concurrency | None = None
    confirm: bool | None = None

    @model_validator(mode="after")
    def _unique(self) -> Self:
        if self.args is not None:
            _unique_names(self.args, "Argument")
        if self.secret_env is not None:
            _unique_names(self.secret_env, "Secret variable")
        return self


class ActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    executor: Literal["local", "ssh", "http"]
    target_id: uuid.UUID | None
    spec: ScriptSpec
    args: list[ArgSpec]
    secret_env: list[SecretEnv]
    timeout_seconds: int
    concurrency: Concurrency
    confirm: bool
    created_at: datetime
    updated_at: datetime


ArgValue = str | int | bool


class RunRequest(BaseModel):
    args: dict[str, ArgValue] = Field(default_factory=dict)
