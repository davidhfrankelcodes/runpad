"""The Home Assistant entity feature: buttons by domain, state parsing, and real requests."""

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features import home_assistant
from app.features.base import ProbeResult
from app.models import Executor, StateTone
from app.schemas.actions import HttpSpec
from tests.fakes import FakeHttpServer
from tests.helpers import enable_feature, managed_actions, run_and_wait

TARGET = uuid.uuid4()


def _config(entity_id: str, name: str = "Kitchen") -> home_assistant.ConfigModel:
    return home_assistant.ConfigModel(target_id=TARGET, entity_id=entity_id, name=name)


def _state(
    config: home_assistant.ConfigModel,
    exit_code: int | None,
    output: str = "",
    error: str | None = None,
) -> tuple[str, StateTone, str]:
    [state] = home_assistant.parse(config, ProbeResult(exit_code, output, error))
    return state.value, state.tone, state.detail


def _answer(state: str, **attributes: object) -> str:
    entity = {"entity_id": "x.y", "state": state, "attributes": attributes}
    return "HTTP 200 OK\n" + json.dumps(entity)


def test_switchable_entities_get_on_off_and_toggle() -> None:
    built = home_assistant.build(_config("light.kitchen"))
    assert [(a.key, a.name) for a in built.actions] == [
        ("on", "Turn on Kitchen"),
        ("off", "Turn off Kitchen"),
        ("toggle", "Toggle Kitchen"),
    ]
    on = built.actions[0]
    assert on.executor == Executor.HTTP
    assert on.spec == HttpSpec(
        method="POST",
        path="api/services/homeassistant/turn_on",
        body={"entity_id": "light.kitchen"},
    )
    assert [(t.state_key, t.label) for t in built.tiles] == [("state", "Kitchen")]


def test_scenes_and_scripts_get_one_button() -> None:
    scene = home_assistant.build(_config("scene.movie_night", "Movie night"))
    assert [(a.key, a.name) for a in scene.actions] == [("run", "Activate Movie night")]
    assert scene.actions[0].spec == HttpSpec(
        method="POST", path="api/services/scene/turn_on", body={"entity_id": "scene.movie_night"}
    )
    assert scene.tiles == []  # A scene's state is only when it last ran.
    script = home_assistant.build(_config("script.good_night", "Good night"))
    assert [a.name for a in script.actions] == ["Run Good night"]
    assert len(script.tiles) == 1


def test_sensors_only_get_a_tile() -> None:
    built = home_assistant.build(_config("sensor.outside_temperature", "Outside"))
    assert built.actions == []
    assert [t.label for t in built.tiles] == ["Outside"]


@pytest.mark.parametrize("entity_id", ["kitchen", "light.", "Light.kitchen", "light.a b", "a.b/c"])
def test_rejects_bad_entity_ids(entity_id: str) -> None:
    with pytest.raises(ValidationError):
        _config(entity_id)


def test_probe_reads_the_entity() -> None:
    probe = home_assistant.probe(_config("light.kitchen"))
    assert probe.executor == Executor.HTTP
    assert probe.target_id == TARGET
    assert probe.spec == HttpSpec(method="GET", path="api/states/light.kitchen")


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (_answer("on", friendly_name="Kitchen"), ("on", StateTone.GOOD, "")),
        (_answer("off"), ("off", StateTone.NEUTRAL, "")),
        (_answer("unavailable"), ("unavailable", StateTone.UNKNOWN, "")),
        (_answer("21.5", unit_of_measurement="°C"), ("21.5 °C", StateTone.NEUTRAL, "")),
        (_answer("home"), ("home", StateTone.GOOD, "")),
        (
            "HTTP 200 OK\nnot json",
            ("unknown", StateTone.UNKNOWN, "Unexpected answer from Home Assistant"),
        ),
    ],
)
def test_parse(output: str, expected: tuple) -> None:
    assert _state(_config("light.kitchen"), 0, output) == expected


def test_parse_failures() -> None:
    config = _config("light.kitchen")
    assert _state(config, 404, 'HTTP 404 Not Found\n{"message": "Entity not found."}') == (
        "not found",
        StateTone.BAD,
        "No entity light.kitchen",
    )
    assert _state(config, 401, "HTTP 401 Unauthorized\n401: Unauthorized") == (
        "unknown",
        StateTone.UNKNOWN,
        "Home Assistant rejected the token",
    )
    assert _state(config, 502, "HTTP 502 Bad Gateway\n") == (
        "unknown",
        StateTone.UNKNOWN,
        "HTTP 502 Bad Gateway",
    )
    assert _state(config, None, error="Request failed: connection refused") == (
        "unknown",
        StateTone.UNKNOWN,
        "Request failed: connection refused",
    )


def test_buttons_call_the_service_with_the_token(admin_client: TestClient) -> None:
    with FakeHttpServer(required_token="llat") as server:
        secret = admin_client.post(
            "/api/v1/secrets", json={"name": "ha", "kind": "text", "value": "llat"}
        ).json()
        target = admin_client.post(
            "/api/v1/targets",
            json={
                "kind": "http",
                "name": "ha",
                "secret_id": secret["id"],
                "config": {"base_url": server.url},
            },
        ).json()
        instance = enable_feature(
            admin_client,
            "home_assistant",
            {"target_id": target["id"], "entity_id": "switch.fan", "name": "Fan"},
        )
        run = run_and_wait(admin_client, managed_actions(admin_client, instance)["Toggle Fan"])
    assert run["status"] == "succeeded", run
    toggle = next(r for r in server.requests if r["method"] == "POST")
    assert toggle["path"] == "/api/services/homeassistant/toggle"
    assert toggle["body"] == {"entity_id": "switch.fan"}
    assert toggle["authorization"] == "Bearer llat"
