"""The event bus, and /api/v1/events against a real server with polling on."""

import asyncio
import json
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2 as httpx
import pytest

from app.events import QUEUE_SIZE, Event, EventBus
from app.security import CSRF_HEADER, CSRF_HEADER_VALUE
from tests.conftest import ADMIN
from tests.fakes import FakeSshServer, fake_ssh_server
from tests.helpers import create_ssh_target

MEMBER = {"username": "member", "password": "member password 123"}

# --- EventBus --------------------------------------------------------------


async def _drain(bus: EventBus) -> list[str]:
    names: list[str] = []
    with bus.subscribe() as subscription:
        bus.publish(Event(name="run", data={"n": 1}))
        bus.publish(Event(name="state", data={"n": 2}))
        bus.close()
        async for event in subscription.follow():
            assert event is not None
            names.append(event.name)
    return names


def test_close_ends_streams() -> None:
    # close() wakes the stream, which ends without delivering what was still queued.
    assert asyncio.run(_drain(EventBus())) == []


async def _overflow() -> tuple[bool, list[Event | None]]:
    bus = EventBus()
    seen: list[Event | None] = []
    with bus.subscribe() as subscription:
        for n in range(QUEUE_SIZE + 1):
            bus.publish(Event(name="run", data={"n": n}))
        async for event in subscription.follow():
            seen.append(event)
        with bus.subscribe() as fresh:
            bus.publish(Event(name="run", data={}))
            return subscription.dropped and fresh.queue.qsize() == 1, seen


def test_slow_subscribers_are_dropped() -> None:
    dropped, seen = asyncio.run(_overflow())
    assert dropped
    assert seen == []  # The stream ends; the browser reconnects and refetches.


async def _live_order() -> list[int]:
    bus = EventBus()
    got: list[int] = []
    with bus.subscribe() as subscription:

        async def publish() -> None:
            for n in range(3):
                bus.publish(Event(name="run", data={"n": n}))
                await asyncio.sleep(0)
            bus.close()

        task = asyncio.create_task(publish())
        async for event in subscription.follow():
            assert event is not None
            got.append(event.data["n"])
        await task
    return got


def test_bus_delivers_events_in_order() -> None:
    assert asyncio.run(_live_order()) == [0, 1, 2]


# --- /api/v1/events --------------------------------------------------------


class SseReader:
    """Follows an event stream in a thread and collects (event, data) pairs."""

    def __init__(self, client: httpx.Client) -> None:
        self.events: list[tuple[str, dict]] = []
        self._client = client
        self._connected = threading.Event()
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()
        assert self._connected.wait(10), "event stream did not connect"

    def _read(self) -> None:
        name = None
        try:
            with self._client.stream("GET", "/api/v1/events", timeout=30) as stream:
                for line in stream.iter_lines():
                    if line == "event: ready":
                        self._connected.set()
                    elif line.startswith("event: "):
                        name = line.removeprefix("event: ")
                    elif line.startswith("data: ") and name:
                        self.events.append((name, json.loads(line.removeprefix("data: "))))
        except Exception:  # noqa: S110 - the test closed the client mid-stream.
            pass

    def wait_for(self, predicate: Callable[[str, dict], bool], timeout: float = 15) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for name, data in list(self.events):
                if predicate(name, data):
                    return data
            time.sleep(0.05)
        raise AssertionError(f"no matching event; got {self.events}")


def _browser(live_url: str) -> httpx.Client:
    return httpx.Client(base_url=live_url, headers={CSRF_HEADER: CSRF_HEADER_VALUE})


@pytest.fixture
def browsers(live_url: str) -> Iterator[tuple[httpx.Client, httpx.Client, str]]:
    """An admin and a logged-in member, and the member's user id."""
    admin, member = _browser(live_url), _browser(live_url)
    try:
        assert admin.post("/api/v1/setup", json=ADMIN).status_code == 201
        member_id = admin.post("/api/v1/users", json=MEMBER).json()["id"]
        assert member.post("/api/v1/auth/login", json=MEMBER).status_code == 200
        yield admin, member, member_id
    finally:
        admin.close()
        member.close()


def _run(client: httpx.Client, action_id: str) -> dict:
    response = client.post(f"/api/v1/actions/{action_id}/run", json={"args": {}})
    assert response.status_code == 202, response.text
    return response.json()


def test_events_require_login(live_url: str) -> None:
    with _browser(live_url) as anonymous:
        assert anonymous.get("/api/v1/events").status_code == 401


def test_run_events_reach_admins_and_only_the_member_who_ran(
    browsers: tuple[httpx.Client, httpx.Client, str],
) -> None:
    admin, member, member_id = browsers
    action = admin.post(
        "/api/v1/actions",
        json={"name": "hi", "executor": "local", "spec": {"script": "echo hi"}},
    ).json()
    pad = admin.post("/api/v1/pads", json={"name": "Home", "member_ids": [member_id]}).json()
    admin.post(f"/api/v1/pads/{pad['id']}/buttons", json={"action_id": action["id"], "label": "Hi"})
    admin_events, member_events = SseReader(admin), SseReader(member)

    admins_run = _run(admin, action["id"])
    admin_events.wait_for(
        lambda n, d: n == "run" and d["id"] == admins_run["id"] and d["status"] == "succeeded"
    )
    members_run = _run(member, action["id"])
    for reader in (admin_events, member_events):
        started = reader.wait_for(lambda n, d: n == "run" and d["id"] == members_run["id"])
        assert started["status"] == "running"
        assert started["triggered_by"] == "member"
        reader.wait_for(
            lambda n, d: n == "run" and d["id"] == members_run["id"] and d["status"] == "succeeded"
        )
    # The member's stream has passed the admin's Run without showing it.
    assert {d["id"] for _, d in member_events.events} == {members_run["id"]}


def test_state_events_follow_tile_visibility(
    browsers: tuple[httpx.Client, httpx.Client, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, member, member_id = browsers
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\necho running\n")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

    with fake_ssh_server() as server:
        target = _live_ssh_target(admin, server)
        shared = admin.post("/api/v1/pads", json={"name": "Shared", "member_ids": [member_id]})
        private = admin.post("/api/v1/pads", json={"name": "Private"})
        admin_events, member_events = SseReader(admin), SseReader(member)

        def enable(container: str, pad: dict) -> dict:
            response = admin.post(
                "/api/v1/feature-instances",
                json={
                    "feature_id": "docker_container",
                    "name": container,
                    "config": {"target_id": target["id"], "container": container},
                    "pad_id": pad["id"],
                },
            )
            assert response.status_code == 201, response.text
            return response.json()

        hidden = enable("hidden", private.json())
        visible = enable("visible", shared.json())

        # Enabling polls right away; admins see every State.
        for instance in (hidden, visible):
            state = admin_events.wait_for(
                lambda n, d, i=instance: n == "state" and d["feature_instance_id"] == i["id"]
            )
            assert (state["key"], state["value"], state["tone"]) == ("status", "running", "good")
        member_events.wait_for(
            lambda n, d: n == "state" and d["feature_instance_id"] == visible["id"]
        )

        # A Run the member can see marks a point after both State events.
        action = admin.post(
            "/api/v1/actions",
            json={"name": "mark", "executor": "local", "spec": {"script": "true"}},
        ).json()
        pad_id = shared.json()["id"]
        admin.post(f"/api/v1/pads/{pad_id}/buttons", json={"action_id": action["id"], "label": "m"})
        mark = _run(member, action["id"])
        member_events.wait_for(lambda n, d: n == "run" and d["id"] == mark["id"])
        instance_ids = {d["feature_instance_id"] for n, d in member_events.events if n == "state"}
        assert instance_ids == {visible["id"]}


def _live_ssh_target(client: httpx.Client, server: FakeSshServer) -> dict:
    # create_ssh_target only needs .post(...).json() and .status_code, as httpx provides.
    return create_ssh_target(client, server)  # type: ignore[arg-type]


def test_feature_runs_refresh_state_right_away(
    browsers: tuple[httpx.Client, httpx.Client, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admin, _, _ = browsers
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\necho running\n")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")

    with fake_ssh_server() as server:
        target = _live_ssh_target(admin, server)
        events = SseReader(admin)
        instance = admin.post(
            "/api/v1/feature-instances",
            json={
                "feature_id": "docker_container",
                "name": "web",
                "config": {"target_id": target["id"], "container": "web"},
            },
        ).json()
        events.wait_for(lambda n, d: n == "state" and d["value"] == "running")

        # "docker stop" now makes "docker inspect" report exited.
        docker.write_text(
            '#!/bin/sh\n[ "$1" = stop ] && touch "$0.stopped"\n'
            '[ -e "$0.stopped" ] && echo exited || echo running\n'
        )
        stop = next(
            a
            for a in admin.get("/api/v1/actions").json()
            if a["feature_instance_id"] == instance["id"] and a["name"] == "Stop web"
        )
        started = time.monotonic()
        _run(admin, stop["id"])
        events.wait_for(lambda n, d: n == "state" and d["value"] == "stopped", timeout=10)
        # Well before the 30 second poll interval.
        assert time.monotonic() - started < 10
