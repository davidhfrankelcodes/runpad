import pytest
from pydantic import TypeAdapter, ValidationError

from app.errors import DomainError
from app.runner import build_script_request, validate_args
from app.schemas.actions import ArgSpec, ScriptSpec

specs_adapter = TypeAdapter(list[ArgSpec])

SPECS = specs_adapter.validate_python(
    [
        {"name": "container", "type": "string", "pattern": "[a-z0-9_-]+"},
        {"name": "count", "type": "integer", "min": 1, "max": 5, "default": 1},
        {"name": "mode", "type": "enum", "choices": ["soft", "hard"], "default": "soft"},
        {"name": "force", "type": "boolean"},
    ]
)


def test_fills_defaults() -> None:
    assert validate_args(SPECS, {"container": "web"}) == {
        "container": "web",
        "count": 1,
        "mode": "soft",
        "force": False,
    }


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({}, "container: required"),
        ({"container": "web; rm -rf /"}, "container: must match"),
        ({"container": "web", "count": 9}, "count: must be between 1 and 5"),
        ({"container": "web", "count": "2"}, "count: must be an integer"),
        ({"container": "web", "count": True}, "count: must be an integer"),
        ({"container": "web", "mode": "x"}, "mode: must be one of"),
        ({"container": "web", "force": "yes"}, "force: must be true or false"),
        ({"container": "web", "extra": "1"}, "Unknown arguments: extra"),
        ({"container": "we\x00b"}, "container: must match"),
    ],
)
def test_rejects_invalid_values(values: dict, message: str) -> None:
    with pytest.raises(DomainError, match=message):
        validate_args(SPECS, values)


def test_string_must_match_whole_pattern() -> None:
    with pytest.raises(DomainError):
        validate_args(SPECS, {"container": "web\nrm"})


def test_build_request_passes_args_as_env_and_positional() -> None:
    values = validate_args(SPECS, {"container": "web", "force": True})
    request = build_script_request(ScriptSpec(script="true"), SPECS, values, {"TOKEN": "t"})
    assert request.positional == ["web", "1", "soft", "true"]
    assert request.env == {
        "TOKEN": "t",
        "ARG_CONTAINER": "web",
        "ARG_COUNT": "1",
        "ARG_MODE": "soft",
        "ARG_FORCE": "true",
    }
    assert request.script == "true"


@pytest.mark.parametrize(
    "spec",
    [
        {"name": "x", "type": "string", "pattern": "("},
        {"name": "x", "type": "string", "pattern": "[a-z]+", "default": "ABC"},
        {"name": "x", "type": "integer", "min": 5, "max": 1},
        {"name": "x", "type": "enum", "choices": ["a", "a"]},
        {"name": "Bad-Name", "type": "boolean"},
    ],
)
def test_invalid_arg_definitions_are_rejected(spec: dict) -> None:
    with pytest.raises(ValidationError):
        specs_adapter.validate_python([spec])
