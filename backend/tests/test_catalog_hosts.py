"""Host features over SSH: resources, package updates, Proxmox, libvirt, and ZFS."""

import os
import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features import apt_updates, host_resources, libvirt_vm, proxmox_guest, zfs_pool
from app.features.base import ProbeResult
from app.models import StateTone
from app.schemas.actions import ScriptSpec
from tests.fakes import FakeSshServer, fake_ssh_server
from tests.helpers import create_ssh_target, enable_feature, managed_actions, run_and_wait

TARGET = uuid.uuid4()
FakeBin = Callable[[str, str], Path]


@pytest.fixture
def ssh_server() -> Iterator[FakeSshServer]:
    with fake_ssh_server() as server:
        yield server


def _states(
    parse: Callable,
    config: object,
    exit_code: int | None,
    output: str = "",
    error: str | None = None,
) -> list[tuple[str, str, StateTone, str]]:
    return [
        (s.key, s.value, s.tone, s.detail)
        for s in parse(config, ProbeResult(exit_code, output, error))
    ]


def _state(
    parse: Callable,
    config: object,
    exit_code: int | None,
    output: str = "",
    error: str | None = None,
) -> tuple[str, StateTone, str]:
    [(_, value, tone, detail)] = _states(parse, config, exit_code, output, error)
    return value, tone, detail


def _sh(spec: object, extra_env: dict[str, str] | None = None) -> ProbeResult:
    assert isinstance(spec, ScriptSpec)
    result = subprocess.run(  # noqa: S603 - the feature's own fixed script
        ["/bin/sh", "-c", spec.script],
        env={**os.environ, **spec.env, **(extra_env or {})},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return ProbeResult(result.returncode, result.stdout + result.stderr)


def _fake_sudo(fake_bin: FakeBin) -> None:
    # The fake SSH server runs commands as the test user, who is usually not root.
    fake_bin("sudo", '[ "$1" = -n ] && shift\nexec "$@"')


# --- Host resources --------------------------------------------------------

RESOURCES = host_resources.ConfigModel(target_id=TARGET, name="NAS", disk_path="/srv")

RESOURCES_OUTPUT = """load 0.52 0.40 0.31 4
memory 8000000 2000000
disk 1000000000 600000000 350000000
"""


def test_resources_build() -> None:
    built = host_resources.build(RESOURCES)
    assert built.actions == []
    assert [(t.state_key, t.label) for t in built.tiles] == [
        ("load", "NAS CPU load"),
        ("memory", "NAS memory"),
        ("disk", "NAS disk"),
    ]
    spec = host_resources.probe(RESOURCES).spec
    assert isinstance(spec, ScriptSpec)
    assert spec.env == {"DISK_PATH": "/srv"}
    assert "/srv" not in spec.script


def test_resources_parse() -> None:
    assert _states(host_resources.parse, RESOURCES, 0, RESOURCES_OUTPUT) == [
        ("load", "0.52", StateTone.GOOD, "0.40 / 0.31 over 5 / 15 min · 4 cores"),
        ("memory", "75% used", StateTone.GOOD, "5.7 GiB of 7.6 GiB"),
        ("disk", "63% full", StateTone.GOOD, "334 GiB free of 954 GiB on /srv"),
    ]


@pytest.mark.parametrize(
    ("output", "key", "tone"),
    [
        ("load 6.0 1 1 4\n", "load", StateTone.WARN),
        ("load 9.0 1 1 4\n", "load", StateTone.BAD),
        ("memory 100 10\n", "memory", StateTone.WARN),
        ("memory 100 2\n", "memory", StateTone.BAD),
        ("disk 100 90 10\n", "disk", StateTone.WARN),
        ("disk 100 97 3\n", "disk", StateTone.BAD),
    ],
)
def test_resources_tones(output: str, key: str, tone: StateTone) -> None:
    states = {s[0]: s for s in _states(host_resources.parse, RESOURCES, 0, output)}
    assert states[key][2] == tone


def test_resources_failures() -> None:
    unreachable = _states(host_resources.parse, RESOURCES, None, error="Connection refused")
    assert [s[1:] for s in unreachable] == [
        ("unknown", StateTone.UNKNOWN, "Connection refused")
    ] * 3
    missing = _states(host_resources.parse, RESOURCES, 3, "load 0.1 0.1 0.1 2\nmemory 10 5\n")
    assert missing[2] == ("disk", "not found", StateTone.BAD, "No such path: /srv")
    assert missing[0][2] == StateTone.GOOD


def test_resources_probe_reads_this_machine() -> None:
    config = host_resources.ConfigModel(target_id=TARGET, name="x", disk_path="/")
    states = _states(host_resources.parse, config, *_result(_sh(host_resources.probe(config).spec)))
    assert [s[0] for s in states] == ["load", "memory", "disk"]
    assert all(s[2] != StateTone.UNKNOWN for s in states), states

    missing = host_resources.ConfigModel(target_id=TARGET, name="x", disk_path="/no/such/dir")
    result = _sh(host_resources.probe(missing).spec)
    assert result.exit_code == 3
    assert _states(host_resources.parse, missing, *_result(result))[2][1] == "not found"


def _result(result: ProbeResult) -> tuple[int | None, str]:
    return result.exit_code, result.output


# --- Package updates -------------------------------------------------------

APT = apt_updates.ConfigModel(target_id=TARGET, name="NAS")

APT_PLAN = """Reading package lists...
Building dependency tree...
Reading state information...
Calculating upgrade...
The following packages will be upgraded:
  libssl3 openssl tzdata
3 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
Inst libssl3 [3.0.11-1~deb12u1] (3.0.11-1~deb12u2 Debian-Security:12/stable-security [amd64])
Inst openssl [3.0.11-1~deb12u1] (3.0.11-1~deb12u2 Debian-Security:12/stable-security [amd64])
Inst tzdata [2024a-0+deb12u1] (2025b-0+deb12u1 Debian:12.11/stable-updates [all])
Conf libssl3 (3.0.11-1~deb12u2 Debian-Security:12/stable-security [amd64])
"""


def test_apt_build() -> None:
    built = apt_updates.build(APT)
    by_key = {a.key: a for a in built.actions}
    assert list(by_key) == ["refresh", "upgrade"]
    assert by_key["upgrade"].confirm is True
    assert by_key["refresh"].confirm is False
    assert by_key["upgrade"].timeout_seconds == 1800
    upgrade = by_key["upgrade"].spec
    assert isinstance(upgrade, ScriptSpec)
    assert "DEBIAN_FRONTEND=noninteractive" in upgrade.script
    assert "--force-confold" in upgrade.script
    assert upgrade.script.endswith(
        " update && root env DEBIAN_FRONTEND=noninteractive apt-get -y "
        "-o Dpkg::Options::=--force-confdef "
        "-o Dpkg::Options::=--force-confold upgrade"
    )
    assert [(t.state_key, t.label) for t in built.tiles] == [("updates", "NAS updates")]


def test_apt_probe_counts_updates(fake_bin: FakeBin) -> None:
    fake_bin("apt-get", f"cat <<'EOF'\n{APT_PLAN}EOF")
    result = _sh(apt_updates.probe(APT).spec)
    assert (result.exit_code, result.output.strip()) == (0, "updates 3 2 0")
    assert _state(apt_updates.parse, APT, *_result(result)) == (
        "3 updates",
        StateTone.WARN,
        "2 security",
    )


def test_apt_probe_without_apt(fake_bin: FakeBin) -> None:
    result = _sh(apt_updates.probe(APT).spec, {"PATH": str(Path(os.environ["PATH"].split(":")[0]))})
    assert result.exit_code == 3
    assert _state(apt_updates.parse, APT, *_result(result))[0] == "no apt"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("updates 0 0 0\n", ("up to date", StateTone.GOOD, "")),
        ("updates 0 0 1\n", ("up to date", StateTone.WARN, "reboot required")),
        ("updates 1 0 0\n", ("1 update", StateTone.WARN, "")),
        ("updates 12 3 1\n", ("12 updates", StateTone.WARN, "3 security · reboot required")),
    ],
)
def test_apt_parse(output: str, expected: tuple) -> None:
    assert _state(apt_updates.parse, APT, 0, output) == expected


def test_apt_parse_failure() -> None:
    output = "E: Could not open lock file /var/lib/dpkg/lock-frontend\n"
    assert _state(apt_updates.parse, APT, 4, output) == (
        "unknown",
        StateTone.UNKNOWN,
        "E: Could not open lock file /var/lib/dpkg/lock-frontend",
    )


# --- Proxmox guest ---------------------------------------------------------

VM = proxmox_guest.ConfigModel(target_id=TARGET, vmid=101, name="Home Assistant")
CT = proxmox_guest.ConfigModel(target_id=TARGET, guest_type="container", vmid=200, name="Pi-hole")


def test_proxmox_build() -> None:
    built = proxmox_guest.build(VM)
    assert [(a.key, a.name, a.confirm) for a in built.actions] == [
        ("start", "Start Home Assistant", False),
        ("shutdown", "Shut down Home Assistant", True),
        ("reboot", "Reboot Home Assistant", False),
    ]
    for action in built.actions:
        spec = action.spec
        assert isinstance(spec, ScriptSpec)
        assert spec.env == {"CLI": "qm", "VMID": "101"}
        assert spec.script.endswith(f'root "$CLI" {action.key} "$VMID"')
    ct_spec = proxmox_guest.build(CT).actions[0].spec
    assert isinstance(ct_spec, ScriptSpec)
    assert ct_spec.env == {"CLI": "pct", "VMID": "200"}


@pytest.mark.parametrize("field", [{"vmid": 99}, {"guest_type": "lxc"}, {"name": ""}])
def test_proxmox_rejects_bad_config(field: dict) -> None:
    with pytest.raises(ValidationError):
        proxmox_guest.ConfigModel(**{"target_id": TARGET, "vmid": 100, "name": "x", **field})


@pytest.mark.parametrize(
    ("config", "exit_code", "output", "expected"),
    [
        (VM, 0, "status: running\n", ("running", StateTone.GOOD, "")),
        (VM, 0, "status: stopped\n", ("stopped", StateTone.BAD, "")),
        (CT, 0, "status: running\n", ("running", StateTone.GOOD, "")),
        (
            VM,
            2,
            "Configuration file 'nodes/pve/qemu-server/101.conf' does not exist\n",
            ("not found", StateTone.BAD, "No VM with ID 101"),
        ),
        (
            CT,
            2,
            "Configuration file 'nodes/pve/lxc/200.conf' does not exist\n",
            ("not found", StateTone.BAD, "No container with ID 200"),
        ),
        (
            VM,
            1,
            "sudo: a password is required\n",
            ("unknown", StateTone.UNKNOWN, "sudo: a password is required"),
        ),
    ],
)
def test_proxmox_parse(config: object, exit_code: int, output: str, expected: tuple) -> None:
    assert _state(proxmox_guest.parse, config, exit_code, output) == expected


def test_proxmox_buttons_run_qm_on_the_node(
    admin_client: TestClient, ssh_server: FakeSshServer, fake_bin: FakeBin, tmp_path: Path
) -> None:
    log = tmp_path / "calls"
    _fake_sudo(fake_bin)
    fake_bin("qm", f'echo "qm $*" >> {log}')
    target = create_ssh_target(admin_client, ssh_server)
    instance = enable_feature(
        admin_client, "proxmox_guest", {"target_id": target["id"], "vmid": 101, "name": "HA"}
    )
    run = run_and_wait(admin_client, managed_actions(admin_client, instance)["Shut down HA"])
    assert run["status"] == "succeeded", run
    assert log.read_text().splitlines() == ["qm shutdown 101"]


# --- libvirt VM ------------------------------------------------------------

LIBVIRT = libvirt_vm.ConfigModel(target_id=TARGET, domain="win11")


def test_libvirt_build() -> None:
    built = libvirt_vm.build(LIBVIRT)
    assert [(a.key, a.confirm) for a in built.actions] == [
        ("start", False),
        ("shutdown", True),
        ("reboot", False),
    ]
    for action in built.actions:
        spec = action.spec
        assert isinstance(spec, ScriptSpec)
        assert spec.script == f'virsh -c qemu:///system {action.key} "$DOMAIN"'
        assert spec.env == {"DOMAIN": "win11"}


@pytest.mark.parametrize("domain", ["", "-x", "a b", "vm;reboot", "$(id)"])
def test_libvirt_rejects_bad_names(domain: str) -> None:
    with pytest.raises(ValidationError):
        libvirt_vm.ConfigModel(target_id=TARGET, domain=domain)


@pytest.mark.parametrize(
    ("exit_code", "output", "expected"),
    [
        (0, "running\n\n", ("running", StateTone.GOOD, "")),
        (0, "shut off\n\n", ("stopped", StateTone.BAD, "")),
        (0, "paused\n\n", ("paused", StateTone.NEUTRAL, "")),
        (0, "in shutdown\n\n", ("shutting down", StateTone.NEUTRAL, "")),
        (0, "crashed\n\n", ("crashed", StateTone.BAD, "")),
        (
            1,
            "error: failed to get domain 'win11'\n",
            ("not found", StateTone.BAD, "No VM named win11"),
        ),
        (
            1,
            "error: failed to connect to the hypervisor\nerror: Permission denied\n",
            ("unknown", StateTone.UNKNOWN, "error: Permission denied"),
        ),
    ],
)
def test_libvirt_parse(exit_code: int, output: str, expected: tuple) -> None:
    assert _state(libvirt_vm.parse, LIBVIRT, exit_code, output) == expected


# --- ZFS pool --------------------------------------------------------------

ZFS = zfs_pool.ConfigModel(target_id=TARGET, pool="tank")


def test_zfs_build() -> None:
    built = zfs_pool.build(ZFS)
    [scrub] = built.actions
    assert scrub.key == "scrub"
    assert isinstance(scrub.spec, ScriptSpec)
    assert scrub.spec.env == {"POOL": "tank"}
    assert "tank" not in scrub.spec.script
    assert 'root zpool scrub -- "$POOL"' in scrub.spec.script
    assert [(t.state_key, t.label) for t in built.tiles] == [("health", "tank")]


@pytest.mark.parametrize("pool", ["", "1tank", "-x", "a b", "tank;reboot"])
def test_zfs_rejects_bad_names(pool: str) -> None:
    with pytest.raises(ValidationError):
        zfs_pool.ConfigModel(target_id=TARGET, pool=pool)


@pytest.mark.parametrize(
    ("exit_code", "output", "expected"),
    [
        (0, "ONLINE\t62%\n", ("online", StateTone.GOOD, "62% full")),
        (0, "ONLINE\t85%\n", ("online", StateTone.WARN, "85% full")),
        (0, "DEGRADED\t40%\n", ("degraded", StateTone.WARN, "40% full")),
        (0, "FAULTED\t40%\n", ("faulted", StateTone.BAD, "40% full")),
        (
            1,
            "cannot open 'tank': no such pool\n",
            ("not found", StateTone.BAD, "No pool named tank"),
        ),
        (
            127,
            "sh: 1: zpool: not found\n",
            ("unknown", StateTone.UNKNOWN, "sh: 1: zpool: not found"),
        ),
    ],
)
def test_zfs_parse(exit_code: int, output: str, expected: tuple) -> None:
    assert _state(zfs_pool.parse, ZFS, exit_code, output) == expected


def test_zfs_probe_runs_zpool(fake_bin: FakeBin) -> None:
    fake_bin("zpool", 'echo "$*" >&2\nprintf "ONLINE\\t12%%\\n"')
    result = _sh(zfs_pool.probe(ZFS).spec)
    assert result.exit_code == 0
    assert "list -H -o health,capacity -- tank" in result.output
    assert "ONLINE\t12%\n" in result.output
