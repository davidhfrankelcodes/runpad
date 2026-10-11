"""A button that sends one fixed request to an HTTP target."""

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.executors.http import placeholders
from app.features.base import ActionTemplate, Build, ButtonTemplate, Feature, HttpTargetId, button
from app.models import ButtonColor, Executor
from app.schemas.actions import HttpSpec


class ConfigModel(BaseModel):
    target_id: HttpTargetId = Field(
        title="Endpoint",
        description="The HTTP target. Its bearer token, if any, is sent with the request.",
    )
    label: str = Field(title="Button label", min_length=1, max_length=64)
    method: Literal["POST", "GET", "PUT", "PATCH", "DELETE"] = Field(default="POST", title="Method")
    path: str = Field(
        default="",
        title="Path",
        description="Relative to the target's base URL; may include a query string.",
        max_length=2000,
    )
    body: str = Field(
        default="",
        title="JSON body",
        description="Optional. Sent as is.",
        max_length=10_000,
        json_schema_extra={"x-multiline": True},
    )

    @field_validator("path")
    @classmethod
    def _no_placeholders_in_path(cls, path: str) -> str:
        if placeholders(path):
            raise ValueError("{name} placeholders are not supported here")
        return path

    @field_validator("body")
    @classmethod
    def _json(cls, body: str) -> str:
        if not body.strip():
            return ""
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict | list):
            raise ValueError("Must be a JSON object or array")
        if placeholders(parsed):
            raise ValueError("{name} placeholders are not supported here")
        return body

    def parsed_body(self) -> dict[str, Any] | list[Any] | None:
        return json.loads(self.body) if self.body else None


def build(config: ConfigModel) -> Build:
    return Build(
        actions=[
            ActionTemplate(
                key="send",
                name=config.label,
                description="",
                executor=Executor.HTTP,
                target_id=config.target_id,
                spec=HttpSpec(method=config.method, path=config.path, body=config.parsed_body()),
                button=ButtonTemplate(label=config.label, color=ButtonColor.SKY),
            )
        ]
    )


FEATURE = Feature(
    id="webhook",
    name="Webhook",
    description="A button that sends a fixed request to an HTTP endpoint.",
    icon="webhook",
    category="Web",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("send", "Send", "Sends a fixed request to an HTTP endpoint."),
    ],
)
