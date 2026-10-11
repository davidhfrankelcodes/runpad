"""The feature framework: what a catalog Feature declares, and what its build() returns.

A Feature turns a validated config into Action and Tile templates. The service in
app/feature_instances.py stores the Actions as ordinary Actions (marked as managed), so
feature buttons run through exactly the same Action, Run, and executor code as custom
buttons. A Feature that reports State also declares a Poll, which poller.py runs on an
interval through the same executors.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.models import ButtonColor, Concurrency, Executor, SecretKind, StateTone, TargetKind
from app.schemas.actions import ArgSpec, HttpSpec, ScriptSpec, SecretEnv

TARGET_KIND_KEY = "x-target-kind"
SECRET_KIND_KEY = "x-secret-kind"  # noqa: S105 - a JSON schema key, not a secret

# Defines `root CMD...` for scripts that need root on the host: runs CMD directly as root,
# otherwise through `sudo -n` (passwordless sudo; it fails instead of prompting).
AS_ROOT = 'root() { if [ "$(id -u)" = 0 ]; then "$@"; else sudo -n "$@"; fi; }\n'

# Config fields that pick a Target. The setup form shows a target picker, and the service
# checks the Target exists and has this kind.
SshTargetId = Annotated[uuid.UUID, Field(json_schema_extra={TARGET_KIND_KEY: TargetKind.SSH.value})]
HttpTargetId = Annotated[
    uuid.UUID, Field(json_schema_extra={TARGET_KIND_KEY: TargetKind.HTTP.value})
]
# A config field that picks a text Secret (a password or API token). The setup form shows a
# secret picker, and the service checks the Secret exists and is text. Scripts get the value
# through `secret_env` on ActionTemplate and Probe, so it is redacted from output and never
# stored in the config.
TextSecretId = Annotated[
    uuid.UUID, Field(json_schema_extra={SECRET_KIND_KEY: SecretKind.TEXT.value})
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
    secret_env: list[SecretEnv] = field(default_factory=list)  # Text secrets as env vars.
    button: ButtonTemplate | None = None  # Placed on the chosen pad when first created.


@dataclass(frozen=True)
class TileTemplate:
    state_key: str  # Which State the tile shows; the Poll reports it under this key.
    label: str


@dataclass(frozen=True)
class Build:
    actions: list[ActionTemplate]
    tiles: list[TileTemplate] = field(default_factory=list)  # Placed on the chosen pad.


@dataclass(frozen=True)
class Probe:
    """A read-only command run by the poller. Probes are not Runs: their result only
    updates State."""

    executor: Executor
    spec: ScriptSpec | HttpSpec
    target_id: uuid.UUID | None = None
    timeout_seconds: int = 15
    secret_env: list[SecretEnv] = field(default_factory=list)  # Redacted from the output.


@dataclass(frozen=True)
class ProbeResult:
    exit_code: int | None  # None when the probe could not run (see error).
    output: str  # stdout and stderr merged, redacted.
    error: str | None = None  # Connection failure, timeout, ...


@dataclass(frozen=True)
class StateValue:
    key: str
    value: str  # Short: shown large on a tile.
    tone: StateTone
    detail: str = ""  # Shown small: latency, or why the value is unknown.


@dataclass(frozen=True)
class Poll[ConfigT: BaseModel]:
    probe: Callable[[ConfigT], Probe]
    parse: Callable[[ConfigT, ProbeResult], list[StateValue]]
    interval_seconds: int = 30


@dataclass(frozen=True)
class CatalogItem:
    """One thing a Feature can add: a single button (an ActionTemplate's `key`) or a single
    tile (a TileTemplate's `state_key`). The catalog lists items; adding one creates exactly
    that button or tile. Names and descriptions are shown before any config is entered."""

    key: str
    kind: Literal["button", "tile"]
    name: str  # Short: "Start", "Status".
    description: str  # What it does, in words, without the config: "Starts the container."


def button(key: str, name: str, description: str) -> CatalogItem:
    return CatalogItem(key=key, kind="button", name=name, description=description)


def tile(key: str, name: str, description: str) -> CatalogItem:
    return CatalogItem(key=key, kind="tile", name=name, description=description)


@dataclass(frozen=True)
class Feature[ConfigT: BaseModel]:
    id: str
    name: str
    description: str
    icon: str  # A name the frontend maps to an icon.
    category: str
    ConfigModel: type[ConfigT]
    build: Callable[[ConfigT], Build]
    items: list[CatalogItem]
    poll: Poll[ConfigT] | None = None

    def item(self, key: str) -> CatalogItem | None:
        return next((item for item in self.items if item.key == key), None)

    def build_item(self, config: ConfigT, key: str) -> Build:
        """What adding the item `key` creates: its one Action or its one Tile. Empty if
        this config does not offer it (a Home Assistant sensor cannot be turned on)."""
        built = self.build(config)
        item = self.item(key)
        if item is None:
            return Build(actions=[])
        if item.kind == "button":
            return Build(actions=[a for a in built.actions if a.key == key])
        return Build(actions=[], tiles=[t for t in built.tiles if t.state_key == key])

    def config_schema(self) -> dict[str, Any]:
        return self.ConfigModel.model_json_schema()

    def secret_fields(self) -> list[str]:
        """Config fields that hold the id of a text Secret."""
        return [
            name
            for name, info in self.ConfigModel.model_fields.items()
            if isinstance(info.json_schema_extra, dict)
            and SECRET_KIND_KEY in info.json_schema_extra
        ]

    def target_fields(self) -> dict[str, TargetKind]:
        """Config fields that hold a Target id, and the kind of Target each needs."""
        result = {}
        for name, info in self.ConfigModel.model_fields.items():
            extra = info.json_schema_extra
            if isinstance(extra, dict) and TARGET_KIND_KEY in extra:
                result[name] = TargetKind(str(extra[TARGET_KIND_KEY]))
        return result
