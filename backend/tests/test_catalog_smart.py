"""The disk health (SMART) feature: its parser against smartctl 7.4 output, and its script
against a stand-in smartctl and sudo."""

import copy
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.features import smart_disk
from app.features.base import ProbeResult
from app.models import StateTone
from app.schemas.actions import ScriptSpec

TARGET = uuid.uuid4()
DATA = Path(__file__).parent / "data" / "smartctl"


def _real(name: str) -> str:
    """Real `smartctl -j -H -A -i` output (serial numbers replaced)."""
    return (DATA / name).read_text()


def _attribute(id_: int, name: str, raw: int, *, prefail: bool, when_failed: str = "") -> dict:
    return {
        "id": id_,
        "name": name,
        "value": 100,
        "worst": 100,
        "thresh": 10 if prefail else 0,
        "when_failed": when_failed,
        "flags": {"value": 51 if prefail else 50, "prefailure": prefail},
        "raw": {"value": raw, "string": str(raw)},
    }


# A SATA hard disk, laid out as smartctl 7.4 reports one (no SATA disk was at hand to read;
# the NVMe reports above are real).
ATA: dict[str, Any] = {
    "smartctl": {"version": [7, 4], "exit_status": 0},
    "device": {"name": "/dev/sda", "info_name": "/dev/sda [SAT]", "type": "sat", "protocol": "ATA"},
    "model_name": "WDC WD40EFRX-68N32N0",
    "smart_support": {"available": True, "enabled": True},
    "smart_status": {"passed": True},
    "ata_smart_attributes": {
        "revision": 16,
        "table": [
            _attribute(1, "Raw_Read_Error_Rate", 0, prefail=True),
            _attribute(5, "Reallocated_Sector_Ct", 0, prefail=True),
            _attribute(9, "Power_On_Hours", 26280, prefail=False),
            _attribute(194, "Temperature_Celsius", 34, prefail=False),
            _attribute(197, "Current_Pending_Sector", 0, prefail=False),
            _attribute(198, "Offline_Uncorrectable", 0, prefail=False),
        ],
    },
    "power_on_time": {"hours": 26280},
    "temperature": {"current": 34},
}


def _ata(**changes: Any) -> dict:
    report = copy.deepcopy(ATA)
    report.update(changes)
    return report


def _with_raw(report: dict, attribute_id: int, raw: int, when_failed: str = "") -> dict:
    for attribute in report["ata_smart_attributes"]["table"]:
        if attribute["id"] == attribute_id:
            attribute["raw"] = {"value": raw, "string": str(raw)}
            attribute["when_failed"] = when_failed
    return report


def _config(**extra: object) -> smart_disk.ConfigModel:
    return smart_disk.ConfigModel.model_validate(
        {"target_id": str(TARGET), "device": "/dev/disk/by-id/ata-WDC_WD40EFRX", **extra}
    )


def _state(result: ProbeResult, config: smart_disk.ConfigModel | None = None) -> tuple:
    [state] = smart_disk.parse(config or _config(), result)
    assert state.key == "health"
    return state.value, state.tone, state.detail


def _report(report: dict, exit_code: int = 0) -> tuple:
    return _state(ProbeResult(exit_code, json.dumps(report, indent=2) + "\n"))


def test_build_is_one_tile_named_after_the_disk() -> None:
    built = smart_disk.build(_config())
    assert built.actions == []
    assert [(t.state_key, t.label) for t in built.tiles] == [("health", "ata-WDC_WD40EFRX")]
    assert smart_disk.build(_config(name="Parity")).tiles[0].label == "Parity"
    probe = smart_disk.probe(_config(device_type="sat"))
    assert isinstance(probe.spec, ScriptSpec)
    assert probe.spec.env == {"DEVICE": "/dev/disk/by-id/ata-WDC_WD40EFRX", "DEVICE_TYPE": "sat"}
    assert "WDC" not in probe.spec.script  # Config reaches the script as env only.


@pytest.mark.parametrize(
    "field",
    [
        {"device": "sda"},
        {"device": "/etc/passwd"},
        {"device": "/dev/sda; reboot"},
        {"device": "/dev/$(reboot)"},
        {"device_type": "-x"},
        {"device_type": "sat; reboot"},
    ],
)
def test_bad_config_is_refused(field: dict) -> None:
    with pytest.raises(ValidationError):
        _config(**field)


def test_a_real_healthy_nvme_drive() -> None:
    assert _state(ProbeResult(0, _real("nvme.json"))) == (
        "healthy",
        StateTone.GOOD,
        "38 °C · 1% worn · 34 days on",
    )


def test_nvme_warning_signs() -> None:
    nvme = json.loads(_real("nvme.json"))
    log = nvme["nvme_smart_health_information_log"]
    log.update(media_errors=3, percentage_used=97)
    assert _report(nvme) == (
        "warning",
        StateTone.WARN,
        "3 media errors · 97% worn · 38 °C · 34 days on",
    )
    log.update(media_errors=0, percentage_used=1, critical_warning=0x02)  # Temperature.
    assert _report(nvme)[:2] == ("warning", StateTone.WARN)
    log["critical_warning"] = 0x04  # Reliability degraded.
    assert _report(nvme) == (
        "failing",
        StateTone.BAD,
        "The drive reports a critical warning · 38 °C · 1% worn · 34 days on",
    )


def test_hard_disk_health() -> None:
    assert _report(ATA) == ("healthy", StateTone.GOOD, "34 °C · 3.0 years on")
    assert _report(_with_raw(_ata(), 5, 8)) == (
        "warning",
        StateTone.WARN,
        "8 reallocated sectors · 34 °C · 3.0 years on",
    )
    pending = _with_raw(_with_raw(_ata(), 197, 1), 198, 2)
    assert (
        _report(pending)[2] == "1 pending sector · 2 uncorrectable sectors · 34 °C · 3.0 years on"
    )
    assert _report(_ata(temperature={"current": 58}))[:2] == ("warning", StateTone.WARN)
    assert _report(_ata(temperature={"current": 58}))[2].startswith("Running hot")
    past = _with_raw(_ata(), 1, 0, when_failed="past")
    assert _report(past)[2].startswith("Raw Read Error Rate failed in the past")


def test_a_failing_hard_disk() -> None:
    # SMART's own verdict, which smartctl also reports with exit bit 3.
    failing = _with_raw(_ata(smart_status={"passed": False}), 5, 1200, when_failed="now")
    assert _report(failing, exit_code=24) == (
        "failing",
        StateTone.BAD,
        "SMART says the disk is failing · Reallocated Sector Ct failed · 34 °C · 3.0 years on",
    )


def test_a_spun_down_disk_is_left_asleep() -> None:
    assert _state(ProbeResult(9, "")) == (
        "asleep",
        StateTone.NEUTRAL,
        "Spun down; checked when it wakes up",
    )


def test_failures() -> None:
    assert _state(ProbeResult(2, _real("no_device.json")), _config(device="/dev/sdz")) == (
        "not found",
        StateTone.BAD,
        "No disk at /dev/sdz",
    )
    assert _state(ProbeResult(2, _real("permission_denied.json"))) == (
        "unknown",
        StateTone.UNKNOWN,
        "Smartctl open device: /dev/nvme0 failed: Permission denied",
    )
    assert _state(ProbeResult(1, _real("unknown_type.json")))[2] == (
        "/dev/nope: Unable to detect device type"
    )
    assert _state(ProbeResult(1, "sudo: a password is required\n")) == (
        "unknown",
        StateTone.UNKNOWN,
        "sudo: a password is required",
    )
    no_smart = {"smartctl": {"exit_status": 4}, "smart_support": {"available": False}}
    assert _report(no_smart, exit_code=4)[0] == "no SMART"
    assert _state(ProbeResult(None, "", error="Host key changed"))[2] == "Host key changed"


def _host(tmp_path: Path, smartctl: str | None) -> dict[str, str]:
    """A PATH with a stand-in smartctl (if any) and a sudo that just runs its command."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tools = {"sudo": '[ "$1" = -n ] && shift\nexec "$@"\n'}
    if smartctl is not None:
        tools["smartctl"] = smartctl
    for name, body in tools.items():
        path = bin_dir / name
        path.write_text(f"#!/bin/sh\n{body}")
        path.chmod(0o755)
    return {"PATH": f"{bin_dir}:/bin"}


def _probe(config: smart_disk.ConfigModel, env: dict[str, str]) -> ProbeResult:
    spec = smart_disk.probe(config).spec
    assert isinstance(spec, ScriptSpec)
    result = subprocess.run(  # noqa: S603 - the feature's own fixed script
        ["/bin/sh", "-c", spec.script],
        env={**os.environ, **env, **spec.env},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return ProbeResult(result.returncode, result.stdout + result.stderr)


def test_probe_passes_the_disk_as_arguments(tmp_path: Path) -> None:
    env = _host(tmp_path, f'echo "args: $*" >&2\ncat {DATA / "nvme.json"}\n')
    result = _probe(_config(device="/dev/nvme0"), env)
    assert "args: -j -n standby,9 -H -A -i /dev/nvme0\n" in result.output
    assert _state(result)[0] == "healthy"
    typed = _probe(_config(device="/dev/sdb", device_type="sat"), env)
    assert "args: -j -n standby,9 -H -A -i -d sat /dev/sdb\n" in typed.output


def test_probe_explains_a_missing_smartctl(tmp_path: Path) -> None:
    result = _probe(_config(), _host(tmp_path, None))
    assert result.exit_code == 3
    assert _state(result)[2] == "smartctl is not installed on this host; install smartmontools"
