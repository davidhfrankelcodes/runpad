"""The feature framework: what a catalog Feature declares, and what its build() returns.

A Feature turns a validated config into Action templates. The service in
app/feature_instances.py stores them as ordinary Actions (marked as managed), so feature
buttons run through exactly the same Action, Run, and executor code as custom buttons.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.models import ButtonColor, Concurrency, Executor, TargetKind
from app.schemas.actions import ArgSpec, HttpSpec, ScriptSpec

TARGET_KIND_KEY = "x-target-kind"

# Config fields that pick a Target. The setup form shows a target picker, and the service
# checks the Target exists and has this kind.
SshTargetId = Annotated[uuid.UUID, Field(json_schema_extra={TARGET_KIND_KEY: TargetKind.SSH.value})]
HttpTargetId = Annotated[
    uuid.UUID, Field(json_schema_extra={TARGET_KIND_KEY: TargetKind.HTTP.value})
]


@dataclass(frozen=True)
class ButtonTemplate:
    label: str
    color: ButtonColor = ButtonColor.SLATE


@dataclass(frozen=True)
class ActionTemplate:
    key: str  # Stable across rebuilds, so edits keep the Action (and its Buttons and Runs).
    name: str
    executor: Executor
    spec: ScriptSpec | HttpSpec
    target_id: uuid.UUID | None = None
    description: str = ""
    args: list[ArgSpec] = field(default_factory=list)
    timeout_seconds: int = 30
    concurrency: Concurrency = Concurrency.REJECT
    confirm: bool = False
    button: ButtonTemplate | None = None  # Placed on the chosen pad when first created.


@dataclass(frozen=True)
class Feature[ConfigT: BaseModel]:
    id: str
    name: str
    description: str
    icon: str  # A name the frontend maps to an icon.
    category: str
    ConfigModel: type[ConfigT]
    build: Callable[[ConfigT], list[ActionTemplate]]

    def config_schema(self) -> dict[str, Any]:
        return self.ConfigModel.model_json_schema()

    def target_fields(self) -> dict[str, TargetKind]:
        """Config fields that hold a Target id, and the kind of Target each needs."""
        result = {}
        for name, info in self.ConfigModel.model_fields.items():
            extra = info.json_schema_extra
            if isinstance(extra, dict) and TARGET_KIND_KEY in extra:
                result[name] = TargetKind(str(extra[TARGET_KIND_KEY]))
        return result
