"""build() and parse() for the starter catalog, and real runs through the fakes."""

import os
import socket
import subprocess
import sys
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features import (
    compose_stack,
    host_power,
    ping_check,
    systemd_service,
    wake_on_lan,
    webhook,
)
from app.features.base import ProbeResult
from app.models import Executor, StateTone
from app.schemas.actions import HttpSpec, ScriptSpec
from tests.fakes import FakeHttpServer, FakeSshServer, fake_ssh_server
from tests.helpers import create_ssh_target, enable_feature, managed_actions, run_and_wait

TARGET = uuid.uuid4()
FakeBin = Callable[[str, str], Path]


@pytest.fixture
def ssh_server() -> Iterator[FakeSshServer]:
    with fake_ssh_server() as server:
        yield server


def _state(
    parse: Callable,
    config: object,
    exit_code: int | None,
    output: str = "",
    error: str | None = None,
) -> tuple[str, StateTone, str]:
    [state] = parse(config, ProbeResult(exit_code, output, error))
    return state.value, state.tone, state.detail


def _script(spec: object) -> ScriptSpec:
    assert isinstance(spec, ScriptSpec)
    return spec


# --- Docker Compose stack --------------------------------------------------

COMPOSE = compose_stack.ConfigModel(target_id=TARGET, project_dir="/srv/media", name="Media")


def test_compose_build() -> None:
    built = compose_stack.build(COMPOSE)
    by_key = {a.key: a for a in built.actions}
    assert list(by_key) == ["up", "down", "update"]
    assert by_key["down"].confirm is True
    assert by_key["update"].name == "Update Media"
    for action in built.actions:
        spec = _script(action.spec)
        assert spec.env == {"PROJECT_DIR": "/srv/media"}
        assert spec.script.startswith('cd "$PROJECT_DIR" || exit 3\n')
        assert "/srv/media" not in spec.script
    assert _script(by_key["update"].spec).script.endswith(
        "docker compose pull && docker compose up -d"
    )
    assert [(t.state_key, t.label) for t in built.tiles] == [("services", "Media")]


@pytest.mark.parametrize("project_dir", ["relative/path", "", "/a\nb"])
def test_compose_rejects_bad_directories(project_dir: str) -> None:
    with pytest.raises(ValidationError):
        compose_stack.ConfigModel(target_id=TARGET, project_dir=project_dir, name="x")


@pytest.mark.parametrize(
    ("exit_code", "output", "error", "expected"),
    [
        (0, "3 3\n", None, ("3/3 up", StateTone.GOOD, "")),
        (0, "1 3\n", None, ("1/3 up", StateTone.NEUTRAL, "")),
        (0, "0 2\n", None, ("0/2 up", StateTone.BAD, "")),
        (0, "0 0\n", None, ("0/0 up", StateTone.BAD, "")),
        (
            3,
            "sh: cd: can't cd to /srv/media\n",
            None,
            ("not found", StateTone.BAD, "No directory /srv/media"),
        ),
        (
            4,
            "no configuration file provided: not found\n",
            None,
            ("unknown", StateTone.UNKNOWN, "no configuration file provided: not found"),
        ),
        (None, "", "Could not connect", ("unknown", StateTone.UNKNOWN, "Could not connect")),
    ],
)
def test_compose_parse(
    exit_code: int | None, output: str, error: str | None, expected: tuple
) -> None:
    assert _state(compose_stack.parse, COMPOSE, exit_code, output, error) == expected


def test_compose_probe_counts_services(fake_bin: FakeBin, tmp_path: Path) -> None:
    fake_bin(
        "docker",
        'case "$*" in\n'
        '  "compose ps --services --status running") printf "web\\ndb\\n" ;;\n'
        '  "compose config --services") printf "web\\ndb\\ncache\\n" ;;\n'
        "esac",
    )
    spec = _script(compose_stack.probe(COMPOSE).spec)
    result = subprocess.run(  # noqa: S603 - the feature's own fixed script
        ["/bin/sh", "-c", spec.script],
        env={**os.environ, "PROJECT_DIR": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert (result.returncode, result.stdout) == (0, "2 3\n")


# --- systemd service -------------------------------------------------------

SYSTEMD = systemd_service.ConfigModel(target_id=TARGET, unit="nginx.service")


def test_systemd_build() -> None:
    built = systemd_service.build(SYSTEMD)
    assert [a.key for a in built.actions] == ["start", "stop", "restart"]
    for action in built.actions:
        spec = _script(action.spec)
        assert spec.env == {"UNIT": "nginx.service"}
        assert spec.script.endswith(f'root systemctl {action.key} "$UNIT"')
        assert "nginx" not in spec.script
    assert [a.confirm for a in built.actions] == [False, True, False]


@pytest.mark.parametrize("unit", ["", "-x", "a b", "nginx;reboot", "$(id)"])
def test_systemd_rejects_bad_units(unit: str) -> None:
    with pytest.raises(ValidationError):
        systemd_service.ConfigModel(target_id=TARGET, unit=unit)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("loaded active\n", ("active", StateTone.GOOD, "")),
        ("loaded inactive\n", ("inactive", StateTone.BAD, "")),
        ("loaded failed\n", ("failed", StateTone.BAD, "")),
        ("loaded activating\n", ("activating", StateTone.NEUTRAL, "")),
        ("not-found inactive\n", ("not found", StateTone.BAD, "No unit named nginx.service")),
    ],
)
def test_systemd_parse(output: str, expected: tuple) -> None:
    assert _state(systemd_service.parse, SYSTEMD, 0, output) == expected


def test_systemd_parse_failures() -> None:
    assert _state(systemd_service.parse, SYSTEMD, 127, "sh: systemctl: not found\n") == (
        "unknown",
        StateTone.UNKNOWN,
        "sh: systemctl: not found",
    )


def test_systemd_buttons_use_sudo_unless_root(
    admin_client: TestClient, ssh_server: FakeSshServer, fake_bin: FakeBin, tmp_path: Path
) -> None:
    log = tmp_path / "calls"
    fake_bin("sudo", f'echo "sudo $*" >> {log}\n[ "$1" = -n ] && shift\nexec "$@"')
    fake_bin("systemctl", f'echo "systemctl $*" >> {log}')
    target = create_ssh_target(admin_client, ssh_server)
    instance = enable_feature(
        admin_client, "systemd_service", {"target_id": target["id"], "unit": "nginx"}
    )
    run = run_and_wait(admin_client, managed_actions(admin_client, instance)["Restart nginx"])
    assert run["status"] == "succeeded", run
    expected = ["systemctl restart nginx"]
    if os.getuid() != 0:
        expected.insert(0, "sudo -n systemctl restart nginx")
    assert log.read_text().splitlines() == expected


# --- Host power ------------------------------------------------------------

POWER = host_power.ConfigModel(target_id=TARGET, name="NAS")


def test_power_build_always_confirms() -> None:
    built = host_power.build(POWER)
    assert [(a.key, a.name, a.confirm) for a in built.actions] == [
        ("reboot", "Reboot NAS", True),
        ("shutdown", "Shut down NAS", True),
    ]
    assert "systemctl poweroff" in _script(built.actions[1].spec).script
    assert [t.state_key for t in built.tiles] == ["reachable"]


@pytest.mark.parametrize(
    ("output", "detail"),
    [
        ("300.5 1000.1\n", "up 5 min"),
        ("12345.67 2345.1\n", "up 3 h 25 min"),
        ("200000 1\n", "up 2 d 7 h"),
        ("not linux\n", ""),
    ],
)
def test_power_parse_reachable(output: str, detail: str) -> None:
    assert _state(host_power.parse, POWER, 0, output) == ("reachable", StateTone.GOOD, detail)


def test_power_parse_unreachable() -> None:
    assert _state(host_power.parse, POWER, None, error="Could not connect: timed out") == (
        "unreachable",
        StateTone.BAD,
        "Could not connect: timed out",
    )


def test_power_schedules_the_reboot_outside_the_run(
    admin_client: TestClient, ssh_server: FakeSshServer, fake_bin: FakeBin, tmp_path: Path
) -> None:
    log = tmp_path / "calls"
    fake_bin("sudo", '[ "$1" = -n ] && shift\nexec "$@"')
    fake_bin("systemd-run", f'echo "systemd-run $*" >> {log}')
    target = create_ssh_target(admin_client, ssh_server)
    instance = enable_feature(
        admin_client, "host_power", {"target_id": target["id"], "name": "box"}
    )
    run = run_and_wait(admin_client, managed_actions(admin_client, instance)["Reboot box"])
    assert run["status"] == "succeeded", run
    assert run["output"] == "reboot in 3 seconds\n"
    assert log.read_text() == (
        "systemd-run --quiet --on-active=3 --timer-property=AccuracySec=100ms systemctl reboot\n"
    )


# --- Wake-on-LAN -----------------------------------------------------------


def test_wol_normalizes_the_mac() -> None:
    config = wake_on_lan.ConfigModel(target_id=TARGET, mac="AA-BB-CC-00-11-22", name="Desk")
    assert config.mac == "aa:bb:cc:00:11:22"
    [action] = wake_on_lan.build(config).actions
    spec = _script(action.spec)
    assert spec.env == {"MAC": "aa:bb:cc:00:11:22", "BROADCAST": "255.255.255.255", "PORT": "9"}
    assert "aa:bb" not in spec.script
    assert action.name == "Wake Desk"


@pytest.mark.parametrize(
    "field", [{"mac": "aa:bb:cc:00:11"}, {"mac": "zz:bb:cc:00:11:22"}, {"broadcast": "1.2.3"}]
)
def test_wol_rejects_bad_addresses(field: dict) -> None:
    with pytest.raises(ValidationError):
        wake_on_lan.ConfigModel(
            **{"target_id": TARGET, "mac": "aa:bb:cc:00:11:22", "name": "x", **field}
        )


def test_wol_script_sends_a_magic_packet() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.settimeout(5)
        port = listener.getsockname()[1]
        python_dir = str(Path(sys.executable).parent)
        result = subprocess.run(  # noqa: S603 - the feature's own fixed script
            ["/bin/sh", "-c", wake_on_lan.SEND],
            env={
                "PATH": f"{python_dir}:/usr/bin:/bin",
                "MAC": "aa:bb:cc:00:11:22",
                "BROADCAST": "127.0.0.1",
                "PORT": str(port),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        packet, _ = listener.recvfrom(1024)
    assert packet == b"\xff" * 6 + bytes.fromhex("aabbcc001122") * 16
    assert result.stdout == "Sent a magic packet to aa:bb:cc:00:11:22\n"


# --- Webhook ---------------------------------------------------------------


def test_webhook_build() -> None:
    config = webhook.ConfigModel(
        target_id=TARGET, label="Lights off", path="api/scene?x=1", body='{"on": false}'
    )
    [action] = webhook.build(config).actions
    assert action.executor == Executor.HTTP
    assert action.spec == HttpSpec(method="POST", path="api/scene?x=1", body={"on": False})
    assert action.name == "Lights off"


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ({"body": "{nope"}, "Not valid JSON"),
        ({"body": "3"}, "object or array"),
        ({"body": '{"a": "{x}"}'}, "placeholders"),
        ({"path": "items/{id}"}, "placeholders"),
    ],
)
def test_webhook_rejects_bad_requests(field: dict, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        webhook.ConfigModel(**{"target_id": TARGET, "label": "x", **field})


def test_webhook_sends_the_request(admin_client: TestClient) -> None:
    with FakeHttpServer() as server:
        target = admin_client.post(
            "/api/v1/targets",
            json={"kind": "http", "name": "hook", "config": {"base_url": server.url}},
        ).json()
        instance = enable_feature(
            admin_client,
            "webhook",
            {
                "target_id": target["id"],
                "label": "Deploy",
                "method": "PUT",
                "path": "hooks/deploy",
                "body": '{"ref": "main"}',
            },
        )
        run = run_and_wait(admin_client, managed_actions(admin_client, instance)["Deploy"])
    assert run["status"] == "succeeded", run
    assert server.requests[0]["method"] == "PUT"
    assert server.requests[0]["path"] == "/hooks/deploy"
    assert server.requests[0]["body"] == {"ref": "main"}


# --- Ping check ------------------------------------------------------------

PING = ping_check.ConfigModel(host="nas.lan")

PING_OK = """PING nas.lan (192.168.1.5) 56(84) bytes of data.
64 bytes from 192.168.1.5: icmp_seq=1 ttl=64 time=0.412 ms

--- nas.lan ping statistics ---
1 packets transmitted, 1 received, 0% packet loss, time 0ms
rtt min/avg/max/mdev = 0.412/0.412/0.412/0.000 ms
"""


def test_ping_build_has_a_tile_and_no_buttons() -> None:
    built = ping_check.build(PING)
    assert built.actions == []
    assert [(t.state_key, t.label) for t in built.tiles] == [("ping", "nas.lan")]
    probe = ping_check.probe(PING)
    assert probe.executor == Executor.LOCAL
    assert _script(probe.spec).env == {"HOST": "nas.lan"}
    assert "nas.lan" not in _script(probe.spec).script


@pytest.mark.parametrize("host", ["-f", "a b", "x;y", "$(id)", ""])
def test_ping_rejects_bad_hosts(host: str) -> None:
    with pytest.raises(ValidationError):
        ping_check.ConfigModel(host=host)


@pytest.mark.parametrize(
    ("exit_code", "output", "expected"),
    [
        (0, PING_OK, ("up", StateTone.GOOD, "0.412 ms")),
        (0, "64 bytes from ::1: icmp_seq=1 ttl=64 time<1 ms\n", ("up", StateTone.GOOD, "<1 ms")),
        (
            1,
            "1 packets transmitted, 0 received, 100% packet loss\n",
            ("down", StateTone.BAD, "No reply"),
        ),
        (
            2,
            "ping: nas.lan: Name or service not known\n",
            ("down", StateTone.BAD, "ping: nas.lan: Name or service not known"),
        ),
    ],
)
def test_ping_parse(exit_code: int, output: str, expected: tuple) -> None:
    assert _state(ping_check.parse, PING, exit_code, output) == expected


def test_ping_check_needs_no_target(admin_client: TestClient) -> None:
    pad = admin_client.post("/api/v1/pads", json={"name": "Net"}).json()
    instance = enable_feature(admin_client, "ping_check", {"host": "127.0.0.1"}, pad["id"])
    assert managed_actions(admin_client, instance) == {}
    pad_detail = admin_client.get(f"/api/v1/pads/{pad['id']}").json()
    assert pad_detail["buttons"] == []
    assert [t["label"] for t in pad_detail["tiles"]] == ["127.0.0.1"]
