import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.executors.http import placeholders
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


def _not_reserved(name: str) -> str:
    if name in RESERVED_ENV or name.startswith(("ARG_", "RUNPAD_")):
        raise ValueError(f"{name} is reserved")
    return name


EnvName = Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$"), AfterValidator(_not_reserved)]


class SecretEnv(BaseModel):
    name: EnvName
    secret_id: uuid.UUID


class ScriptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    script: str = Field(
        min_length=1,
        max_length=65_536,
        description="Run with /bin/sh -c. Arguments arrive as $ARG_<NAME> and as $1, $2, ... "
        "in the order they are defined; they are never interpolated into this text.",
    )
    env: dict[EnvName, Annotated[str, Field(max_length=1000, pattern=r"^[^\x00]*$")]] = Field(
        default_factory=dict,
        max_length=20,
        description="Fixed environment variables. Features use these to pass their "
        "configuration to the script without interpolating it.",
    )


class HttpSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    path: str = Field(
        default="",
        max_length=2000,
        description="Relative to the target's base URL; may include a query string. "
        "{name} placeholders are filled with argument values, percent-encoded.",
    )
    body: dict[str, Any] | list[Any] | None = Field(
        default=None,
        description='JSON body. A string that is exactly "{name}" becomes the typed argument '
        "value; {name} inside a longer string is replaced with the value's text.",
    )


def _unique_names(items: list[ArgSpec] | list[SecretEnv], what: str) -> None:
    names = [item.name for item in items]
    if len(set(names)) != len(names):
        raise ValueError(f"{what} names must be unique")


def check_placeholders(spec: "ScriptSpec | HttpSpec", args: list[ArgSpec]) -> None:
    """HTTP templates may only reference defined arguments."""
    if isinstance(spec, HttpSpec):
        used = placeholders(spec.path) | placeholders(spec.body)
        if unknown := used - {arg.name for arg in args}:
            raise ValueError(f"Unknown placeholders: {', '.join(sorted(unknown))}")


ActionName = Annotated[str, Field(min_length=1, max_length=64)]
Description = Annotated[str, Field(max_length=500)]
Timeout = Annotated[int, Field(ge=1, le=3600)]


class _ActionCreateBase(BaseModel):
    name: ActionName
    description: Description = ""
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


class LocalActionCreate(_ActionCreateBase):
    """Runs inside the app container. Cannot touch the host."""

    executor: Literal["local"]
    spec: ScriptSpec


class SshActionCreate(_ActionCreateBase):
    """Runs a script on an SSH target."""

    executor: Literal["ssh"]
    target_id: uuid.UUID
    spec: ScriptSpec


class HttpActionCreate(_ActionCreateBase):
    """Sends a request to an HTTP target. Secret variables are not supported; use the
    target's bearer token."""

    executor: Literal["http"]
    target_id: uuid.UUID
    spec: HttpSpec

    @model_validator(mode="after")
    def _http_rules(self) -> Self:
        if self.secret_env:
            raise ValueError("HTTP actions cannot use secret variables")
        check_placeholders(self.spec, self.args)
        return self


ActionCreate = Annotated[
    LocalActionCreate | SshActionCreate | HttpActionCreate, Field(discriminator="executor")
]


class ActionUpdate(BaseModel):
    """Fields to change. The executor cannot change; `spec` must match it."""

    name: ActionName | None = None
    description: Description | None = None
    target_id: uuid.UUID | None = None
    spec: ScriptSpec | HttpSpec | None = None
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
    feature_instance_id: uuid.UUID | None = Field(
        description="Set when a feature generated this Action; it cannot be edited directly."
    )
    spec: ScriptSpec | HttpSpec
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
