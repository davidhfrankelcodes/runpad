"""Show a Linux host's CPU load, memory use, and disk use, read over SSH."""

from pydantic import BaseModel, Field

from app.features.base import (
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

KEYS = ("load", "memory", "disk")


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host", description="The SSH target, running Linux. No root needed."
    )
    name: str = Field(
        title="Host name", description="Shown on the tiles.", min_length=1, max_length=40
    )
    disk_path: str = Field(
        default="/",
        title="Disk to watch",
        description="A path on the filesystem to report, for example / or /mnt/media.",
        pattern=r"^/[^\x00\n]*$",
        max_length=255,
    )


def build(config: ConfigModel) -> Build:
    return Build(
        actions=[],
        tiles=[
            TileTemplate(state_key="load", label=f"{config.name} CPU load"),
            TileTemplate(state_key="memory", label=f"{config.name} memory"),
            TileTemplate(state_key="disk", label=f"{config.name} disk"),
        ],
    )


# Three lines: "load <1 min> <5 min> <15 min> <cores>", "memory <total KiB> <available KiB>",
# and "disk <size KiB> <used KiB> <available KiB>" (exit 3 if the path is missing).
SCRIPT = """read one five fifteen _ < /proc/loadavg
echo "load $one $five $fifteen $(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"
awk '/^MemTotal:/ {t = $2} /^MemAvailable:/ {a = $2} END {print "memory", t, a}' /proc/meminfo
df -Pk -- "$DISK_PATH" >/dev/null 2>&1 || exit 3
df -Pk -- "$DISK_PATH" | awk 'NR == 2 {print "disk", $2, $3, $4}'
"""


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=ScriptSpec(script=SCRIPT, env={"DISK_PATH": config.disk_path}),
    )


def _gib(kib: int) -> str:
    gib = kib / 1024 / 1024
    return f"{gib:.1f} GiB" if gib < 100 else f"{gib:.0f} GiB"


def _tone(percent: float, warn: float, bad: float) -> StateTone:
    return StateTone.GOOD if percent < warn else StateTone.WARN if percent < bad else StateTone.BAD


def _load(fields: list[str]) -> StateValue:
    one, five, fifteen, cores = float(fields[0]), fields[1], fields[2], int(fields[3]) or 1
    per_core = one / cores
    tone = StateTone.GOOD if per_core < 1 else StateTone.WARN if per_core < 2 else StateTone.BAD
    detail = f"{five} / {fifteen} over 5 / 15 min · {cores} core{'s' if cores != 1 else ''}"
    return StateValue("load", f"{one:g}", tone, detail)


def _memory(fields: list[str]) -> StateValue:
    total, available = int(fields[0]), int(fields[1])
    used = total - available
    percent = 100 * used / total if total else 0
    detail = f"{_gib(used)} of {_gib(total)}"
    return StateValue("memory", f"{percent:.0f}% used", _tone(percent, 85, 95), detail)


def _disk(fields: list[str], path: str) -> StateValue:
    size, used, available = int(fields[0]), int(fields[1]), int(fields[2])
    # As df reports Use%: reserved blocks count as unavailable.
    percent = 100 * used / (used + available) if used + available else 0
    detail = f"{_gib(available)} free of {_gib(size)} on {path}"
    return StateValue("disk", f"{percent:.0f}% full", _tone(percent, 85, 95), detail)


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    if result.error is not None:
        return [StateValue(key, "unknown", StateTone.UNKNOWN, result.error) for key in KEYS]
    found: dict[str, list[str]] = {}
    for line in lines:
        key, *fields = line.split()
        found[key] = fields
    states: list[StateValue] = []
    for key in KEYS:
        try:
            fields = found[key]
            if key == "load":
                states.append(_load(fields))
            elif key == "memory":
                states.append(_memory(fields))
            else:
                states.append(_disk(fields, config.disk_path))
        except (KeyError, IndexError, ValueError):
            if key == "disk" and result.exit_code == 3:
                detail = f"No such path: {config.disk_path}"
                states.append(StateValue(key, "not found", StateTone.BAD, detail))
            else:
                detail = lines[-1] if lines else f"The check exited with {result.exit_code}"
                states.append(StateValue(key, "unknown", StateTone.UNKNOWN, detail))
    return states


FEATURE = Feature(
    id="host_resources",
    name="Host resources",
    description="See a Linux host's CPU load, memory use, and disk use. Turns amber at "
    "85% full and red at 95%.",
    icon="gauge",
    category="System",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        tile("load", "CPU load", "Load average against the number of cores."),
        tile("memory", "Memory", "How much memory is in use."),
        tile("disk", "Disk", "How full a filesystem is."),
    ],
    poll=Poll(probe=probe, parse=parse),
)
