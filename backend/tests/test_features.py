"""The feature framework, the catalog API, and the Docker container feature."""

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features import FEATURES, docker_container
from app.features.base import Feature
from app.models import ButtonColor, Executor, TargetKind
from app.schemas.actions import ScriptSpec
from tests.fakes import FakeSshServer, fake_ssh_server
from tests.helpers import create_ssh_target, wait_for_run


@pytest.fixture
def ssh_server() -> Iterator[FakeSshServer]:
    with fake_ssh_server() as server:
        yield server


# --- Registry and build() --------------------------------------------------


@pytest.mark.parametrize("feature", FEATURES.values(), ids=lambda f: f.id)
def test_registered_features_are_well_formed(feature: Feature[Any]) -> None:
    assert FEATURES[feature.id] is feature
    assert feature.name and feature.description and feature.icon and feature.category
    schema = feature.config_schema()
    assert schema["type"] == "object"
    for name in feature.target_fields():
        assert schema["properties"][name]["x-target-kind"] in {"ssh", "http"}


def test_docker_build_passes_the_container_as_env_never_in_the_script() -> None:
    target_id = uuid.uuid4()
    config = docker_container.ConfigModel(target_id=target_id, container="plex")
    built = docker_container.build(config)
    templates = built.actions

    assert [t.key for t in templates] == ["start", "stop", "restart", "logs"]
    assert [(t.state_key, t.label) for t in built.tiles] == [("status", "plex")]
    for template in templates:
        assert template.executor == Executor.SSH
        assert template.target_id == target_id
        assert isinstance(template.spec, ScriptSpec)
        assert "plex" not in template.spec.script
        assert template.spec.env == {"CONTAINER": "plex"}
        assert template.button is not None
    by_key = {t.key: t for t in templates}
    assert by_key["start"].spec.script == 'docker start "$CONTAINER"'
    assert by_key["logs"].spec.script == 'docker logs --tail 200 "$CONTAINER" 2>&1'
    assert by_key["logs"].confirm is False
    assert by_key["stop"].confirm is True
    assert by_key["start"].confirm is False
    assert by_key["stop"].button.color == ButtonColor.RED
    assert by_key["restart"].name == "Restart plex"
    # Members see descriptions on pads, so they must not spell out the command.
    assert by_key["stop"].description == "Stops the plex container."


def test_docker_target_field_needs_an_ssh_target() -> None:
    assert docker_container.FEATURE.target_fields() == {"target_id": TargetKind.SSH}


@pytest.mark.parametrize("container", ["", "-rm", "a b", "web;reboot", "$(id)", "web\n", "x" * 64])
def test_docker_rejects_unsafe_container_names(container: str) -> None:
    with pytest.raises(ValidationError):
        docker_container.ConfigModel(target_id=uuid.uuid4(), container=container)


@pytest.mark.parametrize("container", ["web", "my-app_1", "app.v2", "A1"])
def test_docker_accepts_container_names(container: str) -> None:
    docker_container.ConfigModel(target_id=uuid.uuid4(), container=container)


# --- API -------------------------------------------------------------------


def _pad(client: TestClient, name: str = "Home") -> dict:
    response = client.post("/api/v1/pads", json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _enable(
    client: TestClient, target: dict, container: str = "web", pad: dict | None = None
) -> dict:
    response = client.post(
        "/api/v1/feature-instances",
        json={
            "feature_id": "docker_container",
            "name": container,
            "config": {"target_id": target["id"], "container": container},
            "pad_id": pad["id"] if pad else None,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _managed(client: TestClient, instance: dict) -> list[dict]:
    actions = client.get("/api/v1/actions").json()
    return [a for a in actions if a["feature_instance_id"] == instance["id"]]


def test_catalog_lists_features_with_their_form(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/features")
    assert response.status_code == 200
    docker = next(f for f in response.json() if f["id"] == "docker_container")
    assert docker["name"] == "Docker container"
    properties = docker["config_schema"]["properties"]
    assert properties["target_id"]["x-target-kind"] == "ssh"
    assert properties["container"]["title"] == "Container name"
    assert set(docker["config_schema"]["required"]) == {"target_id", "container"}


def test_enabling_creates_managed_actions_and_buttons(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    pad = _pad(admin_client)
    instance = _enable(admin_client, target, pad=pad)
    assert instance["feature_id"] == "docker_container"
    assert instance["config"] == {"target_id": target["id"], "container": "web"}

    actions = _managed(admin_client, instance)
    assert sorted(a["name"] for a in actions) == [
        "Logs of web",
        "Restart web",
        "Start web",
        "Stop web",
    ]
    assert all(a["target_id"] == target["id"] for a in actions)

    buttons = admin_client.get(f"/api/v1/pads/{pad['id']}").json()["buttons"]
    assert [b["label"] for b in buttons] == ["Start web", "Stop web", "Restart web", "Logs of web"]
    assert [b["color"] for b in buttons] == ["emerald", "red", "amber", "slate"]
    assert next(b for b in buttons if b["label"] == "Stop web")["action"]["confirm"] is True


def test_enabling_without_a_pad_creates_only_actions(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    instance = _enable(admin_client, target)
    assert len(_managed(admin_client, instance)) == 4


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"feature_id": "nope"}, "Unknown feature"),
        ({"config": {"container": "web"}}, "target_id"),
        ({"config": {"target_id": str(uuid.uuid4()), "container": "web"}}, "target not found"),
        ({"pad_id": str(uuid.uuid4())}, "Pad not found"),
    ],
)
def test_enabling_validates(
    admin_client: TestClient, ssh_server: FakeSshServer, change: dict, message: str
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    body = {
        "feature_id": "docker_container",
        "name": "web",
        "config": {"target_id": target["id"], "container": "web"},
        **change,
    }
    response = admin_client.post("/api/v1/feature-instances", json=body)
    assert response.status_code in {400, 404}, response.text
    assert message in response.json()["detail"]
    assert admin_client.get("/api/v1/actions").json() == []


def test_enabling_rejects_bad_container_name(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    response = admin_client.post(
        "/api/v1/feature-instances",
        json={
            "feature_id": "docker_container",
            "name": "x",
            "config": {"target_id": target["id"], "container": "web; reboot"},
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"].startswith("container:")


def test_enabling_needs_a_target_of_the_right_kind(admin_client: TestClient) -> None:
    http_target = admin_client.post(
        "/api/v1/targets",
        json={"kind": "http", "name": "api", "config": {"base_url": "http://example.test"}},
    ).json()
    response = admin_client.post(
        "/api/v1/feature-instances",
        json={
            "feature_id": "docker_container",
            "name": "web",
            "config": {"target_id": http_target["id"], "container": "web"},
        },
    )
    assert response.status_code == 400
    assert "needs a ssh target" in response.json()["detail"]


def test_managed_actions_cannot_be_edited_or_deleted(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    action = _managed(admin_client, _enable(admin_client, target))[0]

    response = admin_client.patch(
        f"/api/v1/actions/{action['id']}", json={"spec": {"script": "reboot"}}
    )
    assert response.status_code == 409
    assert "managed by a feature" in response.json()["detail"]
    assert admin_client.delete(f"/api/v1/actions/{action['id']}").status_code == 409


def test_changing_config_rebuilds_actions_in_place(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    pad = _pad(admin_client)
    instance = _enable(admin_client, target, pad=pad)
    before = {a["name"]: a["id"] for a in _managed(admin_client, instance)}
    button = admin_client.get(f"/api/v1/pads/{pad['id']}").json()["buttons"][0]
    admin_client.patch(f"/api/v1/buttons/{button['id']}", json={"label": "Go"})

    response = admin_client.patch(
        f"/api/v1/feature-instances/{instance['id']}",
        json={"name": "api", "config": {"target_id": target["id"], "container": "api"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "api"

    after = {a["name"]: a for a in _managed(admin_client, instance)}
    assert sorted(after) == ["Logs of api", "Restart api", "Start api", "Stop api"]
    assert after["Start api"]["id"] == before["Start web"]
    assert after["Start api"]["spec"]["env"] == {"CONTAINER": "api"}
    # Buttons keep pointing at the same Actions. Generated labels follow the config;
    # the one the admin renamed is kept.
    buttons = admin_client.get(f"/api/v1/pads/{pad['id']}").json()["buttons"]
    assert [b["label"] for b in buttons] == ["Go", "Stop api", "Restart api", "Logs of api"]
    assert buttons[0]["action"]["name"] == "Start api"


def test_bad_config_change_leaves_the_instance_alone(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    instance = _enable(admin_client, target)
    response = admin_client.patch(
        f"/api/v1/feature-instances/{instance['id']}",
        json={"config": {"target_id": target["id"], "container": "$(id)"}},
    )
    assert response.status_code == 400
    current = admin_client.get(f"/api/v1/feature-instances/{instance['id']}").json()
    assert current["config"]["container"] == "web"


def test_deleting_an_instance_deletes_what_it_generated(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    pad = _pad(admin_client)
    instance = _enable(admin_client, target, pad=pad)
    custom = admin_client.post(
        "/api/v1/actions", json={"name": "custom", "executor": "local", "spec": {"script": "true"}}
    ).json()
    action = _managed(admin_client, instance)[0]
    run = admin_client.post(f"/api/v1/actions/{action['id']}/run", json={"args": {}}).json()
    wait_for_run(admin_client, run["id"])

    response = admin_client.delete(f"/api/v1/feature-instances/{instance['id']}")
    assert response.status_code == 204
    assert [a["id"] for a in admin_client.get("/api/v1/actions").json()] == [custom["id"]]
    assert admin_client.get(f"/api/v1/pads/{pad['id']}").json()["buttons"] == []
    # The Run stays in the history.
    kept = admin_client.get(f"/api/v1/runs/{run['id']}")
    assert kept.status_code == 200
    assert kept.json()["action_name"] == action["name"]
    # And the target is free to delete again.
    assert admin_client.delete(f"/api/v1/targets/{target['id']}").status_code == 204


def test_members_cannot_use_the_feature_api(
    admin_client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    member = {"username": "member", "password": "member password 123"}
    assert admin_client.post("/api/v1/users", json=member).status_code == 201
    client = make_client()
    assert client.post("/api/v1/auth/login", json=member).status_code == 200
    assert client.get("/api/v1/features").status_code == 403
    assert client.get("/api/v1/feature-instances").status_code == 403


def test_docker_buttons_run_docker_on_the_host(
    admin_client: TestClient,
    ssh_server: FakeSshServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The fake SSH server runs commands with a local shell; give it a fake docker.
    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\necho "docker $*"\n')
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

    target = create_ssh_target(admin_client, ssh_server)
    instance = _enable(admin_client, target, container="my-app_1")
    action = next(a for a in _managed(admin_client, instance) if a["name"] == "Restart my-app_1")
    run = admin_client.post(f"/api/v1/actions/{action['id']}/run", json={"args": {}}).json()
    done = wait_for_run(admin_client, run["id"])

    assert done["status"] == "succeeded", done
    assert done["output"] == "docker restart my-app_1\n"
    assert all("my-app_1" not in command for command in ssh_server.commands)


# --- Moving buttons and fixed env ------------------------------------------


def test_buttons_can_move_between_pads(admin_client: TestClient) -> None:
    home, other = _pad(admin_client), _pad(admin_client, "Other")
    action = admin_client.post(
        "/api/v1/actions", json={"name": "a", "executor": "local", "spec": {"script": "true"}}
    ).json()
    admin_client.post(
        f"/api/v1/pads/{other['id']}/buttons", json={"action_id": action["id"], "label": "x"}
    )
    button = admin_client.post(
        f"/api/v1/pads/{home['id']}/buttons", json={"action_id": action["id"], "label": "y"}
    ).json()

    response = admin_client.patch(f"/api/v1/buttons/{button['id']}", json={"pad_id": other["id"]})
    assert response.status_code == 200, response.text
    assert response.json()["pad_id"] == other["id"]
    assert response.json()["position"] == 1
    assert admin_client.get(f"/api/v1/pads/{home['id']}").json()["buttons"] == []

    missing = admin_client.patch(
        f"/api/v1/buttons/{button['id']}", json={"pad_id": str(uuid.uuid4())}
    )
    assert missing.status_code == 404


def test_script_env_reaches_the_script(admin_client: TestClient) -> None:
    action = admin_client.post(
        "/api/v1/actions",
        json={
            "name": "greet",
            "executor": "local",
            "spec": {"script": 'echo "$GREETING"', "env": {"GREETING": "hi; there"}},
        },
    ).json()
    run = admin_client.post(f"/api/v1/actions/{action['id']}/run", json={"args": {}}).json()
    assert wait_for_run(admin_client, run["id"])["output"] == "hi; there\n"


@pytest.mark.parametrize("name", ["PATH", "ARG_X", "RUNPAD_KEY", "lower"])
def test_script_env_rejects_reserved_names(admin_client: TestClient, name: str) -> None:
    response = admin_client.post(
        "/api/v1/actions",
        json={"name": "x", "executor": "local", "spec": {"script": "true", "env": {name: "v"}}},
    )
    assert response.status_code == 422


def test_pads_say_what_kind_each_item_is(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    pad = _pad(admin_client)
    _enable(admin_client, target, pad=pad)
    admin_client.post(
        "/api/v1/feature-instances",
        json={
            "feature_id": "ping_check",
            "name": "db",
            "config": {"host": "db"},
            "pad_id": pad["id"],
        },
    )
    script = admin_client.post(
        "/api/v1/actions", json={"name": "s", "executor": "local", "spec": {"script": "true"}}
    ).json()
    http_target = admin_client.post(
        "/api/v1/targets",
        json={"kind": "http", "name": "api", "config": {"base_url": "http://example.test"}},
    ).json()
    request = admin_client.post(
        "/api/v1/actions",
        json={"name": "r", "executor": "http", "target_id": http_target["id"], "spec": {}},
    ).json()
    for action in (script, request):
        created = admin_client.post(
            f"/api/v1/pads/{pad['id']}/buttons", json={"action_id": action["id"], "label": "x"}
        )
        assert created.json()["action"]["kind"]["name"].startswith("Custom")

    detail = admin_client.get(f"/api/v1/pads/{pad['id']}").json()
    assert [
        (b["action"]["kind"]["name"], b["action"]["kind"]["icon"]) for b in detail["buttons"]
    ] == [
        *[("Docker container", "container")] * 4,
        ("Custom command", "terminal"),
        ("Custom request", "webhook"),
    ]
    assert [(t["label"], t["kind"]["name"], t["kind"]["icon"]) for t in detail["tiles"]] == [
        ("web", "Docker container", "container"),
        ("db", "Ping check", "ping"),
    ]
