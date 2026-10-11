"""State polling, Tiles, and the Docker container probe."""

import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.events import Event
from app.features import docker_container
from app.features.base import ProbeResult
from app.models import StateTone
from app.poller import Poller
from tests.fakes import FakeSshServer, fake_ssh_server
from tests.helpers import create_ssh_target


@pytest.fixture
def ssh_server() -> Iterator[FakeSshServer]:
    with fake_ssh_server() as server:
        yield server


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[[str, int], None]:
    """A `docker` on the fake SSH server's PATH. Set what `docker inspect` prints."""
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    docker = tmp_path / "docker"

    def set_status(output: str, exit_code: int = 0) -> None:
        docker.write_text(f"#!/bin/sh\nprintf '%s\\n' '{output}'\nexit {exit_code}\n")
        docker.chmod(0o755)

    set_status("running")
    return set_status


# --- Docker probe and parse ------------------------------------------------

CONFIG = docker_container.ConfigModel(target_id=uuid.uuid4(), container="plex")


def _parse(exit_code: int | None, output: str = "", error: str | None = None) -> tuple:
    [state] = docker_container.parse(CONFIG, ProbeResult(exit_code, output, error))
    assert state.key == "status"
    return state.value, state.tone, state.detail


def test_docker_probe_passes_the_container_as_env() -> None:
    probe = docker_container.probe(CONFIG)
    assert probe.target_id == CONFIG.target_id
    assert "plex" not in probe.spec.script  # type: ignore[union-attr]
    assert probe.spec.env == {"CONTAINER": "plex"}  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("running\n", ("running", StateTone.GOOD, "")),
        ("exited\n", ("stopped", StateTone.BAD, "")),
        ("dead\n", ("dead", StateTone.BAD, "")),
        ("paused\n", ("paused", StateTone.NEUTRAL, "")),
        ("restarting\n", ("restarting", StateTone.NEUTRAL, "")),
    ],
)
def test_docker_parse_statuses(output: str, expected: tuple) -> None:
    assert _parse(0, output) == expected


@pytest.mark.parametrize(
    "output", ["Error: No such object: plex\n", "error: no such object: plex\n"]
)
def test_docker_parse_missing_container(output: str) -> None:
    assert _parse(1, output) == ("not found", StateTone.BAD, "No container named plex")


def test_docker_parse_other_failures() -> None:
    assert _parse(127, "sh: docker: not found\n") == (
        "unknown",
        StateTone.UNKNOWN,
        "sh: docker: not found",
    )
    assert _parse(None, error="Could not connect: refused") == (
        "unknown",
        StateTone.UNKNOWN,
        "Could not connect: refused",
    )


# --- Poller against the fake SSH server ------------------------------------


def _pad(client: TestClient, name: str = "Home", member_ids: list[str] | None = None) -> dict:
    response = client.post("/api/v1/pads", json={"name": name, "member_ids": member_ids or []})
    assert response.status_code == 201, response.text
    return response.json()


def _enable(client: TestClient, target: dict, pad: dict | None, container: str = "web") -> dict:
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


def _poll(client: TestClient, instance: dict) -> list[Event]:
    """Poll once in the app's event loop; return the events it published."""
    state = client.app.state  # type: ignore[attr-defined]
    poller: Poller = state.poller
    events: list[Event] = []

    async def run() -> None:
        with state.bus.subscribe() as subscription:
            await poller.poll(uuid.UUID(instance["id"]))
            while not subscription.queue.empty():
                event = subscription.queue.get_nowait()
                assert event is not None
                events.append(event)

    client.portal.call(run)  # type: ignore[union-attr]
    return events


def _tiles(client: TestClient, pad: dict) -> list[dict]:
    return client.get(f"/api/v1/pads/{pad['id']}").json()["tiles"]


def test_enabling_puts_a_tile_on_the_pad(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    pad = _pad(admin_client)
    instance = _enable(admin_client, create_ssh_target(admin_client, ssh_server), pad)
    assert instance["tiles"] == [{"state_key": "status", "label": "web"}]
    [tile] = _tiles(admin_client, pad)
    assert tile["label"] == "web"
    assert tile["state_key"] == "status"
    assert tile["state"] is None  # Not polled yet.


def test_poll_stores_state_and_publishes_changes(
    admin_client: TestClient,
    ssh_server: FakeSshServer,
    fake_docker: Callable[[str, int], None],
) -> None:
    pad = _pad(admin_client)
    instance = _enable(admin_client, create_ssh_target(admin_client, ssh_server), pad)

    events = _poll(admin_client, instance)
    [tile] = _tiles(admin_client, pad)
    assert tile["state"]["value"] == "running"
    assert tile["state"]["tone"] == "good"
    assert [(e.name, e.data.get("value")) for e in events] == [("state", "running"), ("run", None)]
    assert events[0].feature_instance_id == uuid.UUID(instance["id"])
    first_change = tile["state"]["changed_at"]

    # The first State is recorded as a Run, attributed to the system.
    [run] = admin_client.get("/api/v1/runs").json()["runs"]
    assert (run["action_id"], run["action_name"], run["triggered_by"]) == (
        None,
        "Check web",
        "system",
    )
    assert (run["status"], run["exit_code"]) == ("succeeded", 0)
    assert admin_client.get(f"/api/v1/runs/{run['id']}").json()["output"] == "running\n"

    # Unchanged: checked again, but no event, no Run, and the same changed_at.
    assert _poll(admin_client, instance) == []
    assert len(admin_client.get("/api/v1/runs").json()["runs"]) == 1
    [tile] = _tiles(admin_client, pad)
    assert tile["state"]["changed_at"] == first_change
    assert tile["state"]["checked_at"] > first_change

    fake_docker("exited", 0)
    events = _poll(admin_client, instance)
    assert [(e.name, e.data.get("value") or e.data.get("action_name")) for e in events] == [
        ("state", "stopped"),
        ("run", "Check web"),
    ]
    assert events[1].user_id is None  # Only admins receive system Runs.
    [tile] = _tiles(admin_client, pad)
    assert tile["state"]["changed_at"] > first_change
    assert len(admin_client.get("/api/v1/runs").json()["runs"]) == 2
    # The probe's command line carries nothing from the config.
    assert all("web" not in command for command in ssh_server.commands)


def test_poll_reports_connection_failures(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    pad = _pad(admin_client)
    target = create_ssh_target(admin_client, ssh_server, authorized=False)
    instance = _enable(admin_client, target, pad)
    _poll(admin_client, instance)
    state = _tiles(admin_client, pad)[0]["state"]
    assert (state["value"], state["tone"]) == ("unknown", "unknown")
    assert "Authentication failed" in state["detail"]


def test_config_change_clears_state_and_relabels_tiles(
    admin_client: TestClient,
    ssh_server: FakeSshServer,
    fake_docker: Callable[[str, int], None],
) -> None:
    pad = _pad(admin_client)
    target = create_ssh_target(admin_client, ssh_server)
    instance = _enable(admin_client, target, pad)
    _poll(admin_client, instance)
    admin_client.patch(
        f"/api/v1/feature-instances/{instance['id']}",
        json={"config": {"target_id": target["id"], "container": "api"}},
    )
    [tile] = _tiles(admin_client, pad)
    assert tile["label"] == "api"
    assert tile["state"] is None


def test_renamed_tile_keeps_its_label_on_config_change(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    pad = _pad(admin_client)
    target = create_ssh_target(admin_client, ssh_server)
    instance = _enable(admin_client, target, pad)
    tile = _tiles(admin_client, pad)[0]
    admin_client.patch(f"/api/v1/tiles/{tile['id']}", json={"label": "Plex server"})
    admin_client.patch(
        f"/api/v1/feature-instances/{instance['id']}",
        json={"config": {"target_id": target["id"], "container": "api"}},
    )
    assert _tiles(admin_client, pad)[0]["label"] == "Plex server"


def test_poll_of_deleted_instance_is_ignored(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    instance = _enable(admin_client, create_ssh_target(admin_client, ssh_server), None)
    admin_client.delete(f"/api/v1/feature-instances/{instance['id']}")
    assert _poll(admin_client, instance) == []


# --- Tiles API -------------------------------------------------------------


def test_tiles_can_be_moved_relabeled_reordered_removed_and_added_back(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    home, other = _pad(admin_client), _pad(admin_client, "Other")
    target = create_ssh_target(admin_client, ssh_server)
    first = _enable(admin_client, target, home, "web")
    _enable(admin_client, target, home, "db")
    web, db = _tiles(admin_client, home)

    order = admin_client.put(
        f"/api/v1/pads/{home['id']}/tiles/order", json={"ids": [db["id"], web["id"]]}
    )
    assert order.status_code == 204
    assert [t["label"] for t in _tiles(admin_client, home)] == ["db", "web"]

    moved = admin_client.patch(
        f"/api/v1/tiles/{web['id']}", json={"pad_id": other["id"], "label": "Web"}
    )
    assert moved.status_code == 200, moved.text
    assert [t["label"] for t in _tiles(admin_client, other)] == ["Web"]

    assert admin_client.delete(f"/api/v1/tiles/{web['id']}").status_code == 204
    assert _tiles(admin_client, other) == []

    added = admin_client.post(
        f"/api/v1/pads/{other['id']}/tiles",
        json={"feature_instance_id": first["id"], "state_key": "status", "label": "web again"},
    )
    assert added.status_code == 201, added.text
    assert added.json()["state"] is None

    bad_key = admin_client.post(
        f"/api/v1/pads/{other['id']}/tiles",
        json={"feature_instance_id": first["id"], "state_key": "nope", "label": "x"},
    )
    assert bad_key.status_code == 400


def test_deleting_an_instance_removes_its_tiles(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    pad = _pad(admin_client)
    instance = _enable(admin_client, create_ssh_target(admin_client, ssh_server), pad)
    admin_client.delete(f"/api/v1/feature-instances/{instance['id']}")
    assert _tiles(admin_client, pad) == []


def test_members_see_tiles_but_cannot_change_them(
    admin_client: TestClient, make_client: Callable[[], TestClient], ssh_server: FakeSshServer
) -> None:
    member = {"username": "member", "password": "member password 123"}
    member_id = admin_client.post("/api/v1/users", json=member).json()["id"]
    pad = _pad(admin_client, member_ids=[member_id])
    _enable(admin_client, create_ssh_target(admin_client, ssh_server), pad)
    browser = make_client()
    assert browser.post("/api/v1/auth/login", json=member).status_code == 200

    [tile] = browser.get(f"/api/v1/pads/{pad['id']}").json()["tiles"]
    assert tile["label"] == "web"
    assert browser.patch(f"/api/v1/tiles/{tile['id']}", json={"label": "x"}).status_code == 403
    assert browser.delete(f"/api/v1/tiles/{tile['id']}").status_code == 403


def test_detail_changes_are_not_recorded_as_runs(
    admin_client: TestClient,
    ssh_server: FakeSshServer,
    fake_docker: Callable[[str, int], None],
) -> None:
    instance = _enable(admin_client, create_ssh_target(admin_client, ssh_server), None)
    fake_docker("sh: docker: oops", 7)
    _poll(admin_client, instance)
    fake_docker("sh: docker: oops again", 7)
    events = _poll(admin_client, instance)
    # The detail changed (an event), the value and tone did not (no Run).
    assert [e.name for e in events] == ["state"]
    [run] = admin_client.get("/api/v1/runs").json()["runs"]
    assert (run["status"], run["exit_code"]) == ("failed", 7)


def test_members_do_not_see_system_runs(
    admin_client: TestClient, make_client: Callable[[], TestClient], ssh_server: FakeSshServer
) -> None:
    member = {"username": "member", "password": "member password 123"}
    member_id = admin_client.post("/api/v1/users", json=member).json()["id"]
    pad = _pad(admin_client, member_ids=[member_id])
    instance = _enable(admin_client, create_ssh_target(admin_client, ssh_server), pad)
    _poll(admin_client, instance)
    browser = make_client()
    assert browser.post("/api/v1/auth/login", json=member).status_code == 200
    assert browser.get("/api/v1/runs").json()["runs"] == []
