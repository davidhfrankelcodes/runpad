"""Show a disk's SMART health over SSH: failing, warning signs, temperature, and wear.

smartctl (smartmontools 7.0 or later, for JSON) reads the disk as root. A disk that has
spun down is not woken to be checked: the tile says it is asleep until it spins up again.
"""

import json
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, Field

from app.features.base import (
    AS_ROOT,
    Build,
    Feature,
    Poll,
    Probe,
    ProbeResult,
    SshTargetId,
    StateValue,
    TileTemplate,
    tile,
)
from app.models import Executor, StateTone
from app.schemas.actions import ScriptSpec

# smartctl exits with this when the disk is in standby, instead of waking it.
STANDBY_EXIT = 9
# Above these (°C) a disk is running hot: hard disks wear faster from about 55, NVMe drives
# start throttling around 70.
HOT_DISK = 55
HOT_NVME = 70
# NVMe: the share of its rated endurance used.
WORN_PERCENT = 90
# ATA attributes whose raw count of bad sectors should be zero.
BAD_SECTORS = {
    5: "reallocated",
    197: "pending",
    198: "uncorrectable",
}
# NVMe critical warning bits, other than temperature (bit 1): spare below threshold,
# reliability degraded, read-only, volatile memory backup failed.
NVME_TEMPERATURE_BIT = 0x02

SCRIPT = (
    'PATH="$PATH:/usr/sbin:/sbin:/usr/local/sbin"\n'
    + AS_ROOT
    + r"""command -v smartctl >/dev/null || {
  echo "smartctl is not installed on this host; install smartmontools"; exit 3; }
root smartctl -j -n standby,9 -H -A -i ${DEVICE_TYPE:+-d "$DEVICE_TYPE"} "$DEVICE"
"""
)


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target the disk is in. Its user must be root, or allowed to "
        "use sudo without a password; the host needs smartmontools 7.0 or later.",
    )
    device: str = Field(
        title="Disk",
        description="Its path on the host. /dev/disk/by-id/... names stay the same across "
        "reboots; /dev/sda can change. /dev/nvme0 for an NVMe drive.",
        pattern=r"^/dev/[A-Za-z0-9._/:+@-]{1,200}$",
    )
    name: str = Field(
        default="",
        title="Tile label (optional)",
        description="For example Parity disk. Empty shows the disk's file name, such as "
        "nvme0 or ata-WDC_WD40EFRX-68N32N0_WD-WCC7K0123456.",
        max_length=40,
    )
    device_type: str = Field(
        default="",
        title="Device type (optional)",
        description="Only if smartctl cannot tell by itself, as with some USB enclosures "
        "(sat) or RAID controllers (megaraid,0): its -d option.",
        pattern=r"^([a-z][a-z0-9_]{0,31}(,[A-Za-z0-9_+-]{1,16}){0,2})?$",
    )


def _label(config: ConfigModel) -> str:
    return (config.name or PurePosixPath(config.device).name)[:64]


def build(config: ConfigModel) -> Build:
    return Build(actions=[], tiles=[TileTemplate(state_key="health", label=_label(config))])


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=ScriptSpec(
            script=SCRIPT, env={"DEVICE": config.device, "DEVICE_TYPE": config.device_type}
        ),
        timeout_seconds=60,
    )


def _report(output: str) -> dict[str, Any] | None:
    """smartctl's JSON report: the first object in the output."""
    start = output.find("{")
    if start < 0:
        return None
    try:
        report, _ = json.JSONDecoder().raw_decode(output[start:])
    except ValueError:
        return None
    return report if isinstance(report, dict) else None


def _error(report: dict[str, Any]) -> str:
    messages = report.get("smartctl", {}).get("messages", [])
    return next((str(m.get("string", "")) for m in messages if m.get("severity") == "error"), "")


def _age(hours: int) -> str:
    if hours < 48:
        return f"{hours} h on"
    if hours < 2 * 365 * 24:
        return f"{hours // 24} days on"
    return f"{hours / (365 * 24):.1f} years on"


def _plural(count: int, word: str) -> str:
    return f"{count} {word} sector{'' if count == 1 else 's'}"


def _health(report: dict[str, Any]) -> tuple[str, StateTone, list[str]]:
    """The verdict, its tone, and what led to it."""
    failing: list[str] = []
    warnings: list[str] = []
    if report.get("smart_status", {}).get("passed") is False:
        failing.append("SMART says the disk is failing")

    for attribute in report.get("ata_smart_attributes", {}).get("table", []):
        name = str(attribute.get("name", "")).replace("_", " ")
        when = attribute.get("when_failed")
        if when == "now":
            prefail = attribute.get("flags", {}).get("prefailure")
            (failing if prefail else warnings).append(f"{name} failed")
        elif when == "past":
            warnings.append(f"{name} failed in the past")
        raw = attribute.get("raw", {}).get("value")
        if attribute.get("id") in BAD_SECTORS and isinstance(raw, int) and raw > 0:
            warnings.append(_plural(raw, BAD_SECTORS[attribute["id"]]))

    nvme = report.get("nvme_smart_health_information_log", {})
    critical = nvme.get("critical_warning", 0)
    if isinstance(critical, int) and critical & ~NVME_TEMPERATURE_BIT:
        failing.append("the drive reports a critical warning")
    media_errors = nvme.get("media_errors", 0)
    if isinstance(media_errors, int) and media_errors > 0:
        warnings.append(f"{media_errors} media errors")
    used = nvme.get("percentage_used")
    if isinstance(used, int) and used >= WORN_PERCENT:
        warnings.append(f"{used}% worn")

    defects = report.get("scsi_grown_defect_list")
    if isinstance(defects, int) and defects > 0:
        warnings.append(f"{defects} grown defects")

    temperature = report.get("temperature", {}).get("current")
    hot = HOT_NVME if report.get("device", {}).get("protocol") == "NVMe" else HOT_DISK
    if (isinstance(temperature, int) and temperature >= hot) or (
        isinstance(critical, int) and critical & NVME_TEMPERATURE_BIT
    ):
        warnings.append("running hot")

    if failing:
        return "failing", StateTone.BAD, failing + warnings
    if warnings:
        return "warning", StateTone.WARN, warnings
    return "healthy", StateTone.GOOD, []


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    def state(value: str, tone: StateTone, detail: str) -> list[StateValue]:
        return [StateValue("health", value, tone, detail)]

    if result.error is not None:
        return state("unknown", StateTone.UNKNOWN, result.error)
    lines = result.output.strip().splitlines()
    report = _report(result.output)
    if result.exit_code == STANDBY_EXIT:
        return state("asleep", StateTone.NEUTRAL, "Spun down; checked when it wakes up")
    if report is None or "smart_status" not in report:
        error = _error(report) if report else ""
        if "No such device" in error or "No such file" in error:
            return state("not found", StateTone.BAD, f"No disk at {config.device}")
        if report is not None and report.get("smart_support", {}).get("available") is False:
            return state("no SMART", StateTone.UNKNOWN, "This disk does not report SMART")
        detail = error or (lines[-1] if lines else f"smartctl exited with {result.exit_code}")
        return state("unknown", StateTone.UNKNOWN, detail)

    value, tone, reasons = _health(report)
    facts = []
    temperature = report.get("temperature", {}).get("current")
    if isinstance(temperature, int):
        facts.append(f"{temperature} °C")
    used = report.get("nvme_smart_health_information_log", {}).get("percentage_used")
    if isinstance(used, int) and used < WORN_PERCENT:
        facts.append(f"{used}% worn")
    hours = report.get("power_on_time", {}).get("hours")
    if isinstance(hours, int):
        facts.append(_age(hours))
    return state(value, tone, " · ".join([r[0].upper() + r[1:] for r in reasons[:2]] + facts))


FEATURE = Feature(
    id="smart_disk",
    name="Disk health (SMART)",
    description="See whether a disk is healthy, showing warning signs, or failing, with its "
    "temperature and wear. Spun-down disks are left asleep.",
    icon="disk",
    category="Storage",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        tile(
            "health",
            "Health",
            "Healthy, warning signs (bad sectors, heat, wear), or failing.",
        )
    ],
    poll=Poll(probe=probe, parse=parse, interval_seconds=600),
)
