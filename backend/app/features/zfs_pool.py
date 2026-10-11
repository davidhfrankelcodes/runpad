"""Show a ZFS pool's health and how full it is, and start a scrub, over SSH."""

from pydantic import BaseModel, Field

from app.features.base import (
    AS_ROOT,
    ActionTemplate,
    Build,
    ButtonTemplate,
    Feature,
    Poll,
    Probe,
    ProbeResult,
    SshTargetId,
    StateValue,
    TileTemplate,
    button,
    tile,
)
from app.models import ButtonColor, Executor, StateTone
from app.schemas.actions import ScriptSpec

# zpool lives in /usr/sbin or /sbin on most systems, not on a normal user's PATH.
_PATH = 'PATH="$PATH:/usr/sbin:/sbin"\n'
# ZFS slows down as a pool fills; 80% is the usual advice.
WARN_PERCENT = 80


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target with the pool. Reading health needs no root; starting "
        "a scrub needs root or passwordless sudo.",
    )
    pool: str = Field(
        title="Pool name",
        description="As shown by zpool list.",
        pattern=r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$",
    )


def _spec(script: str, config: ConfigModel) -> ScriptSpec:
    return ScriptSpec(script=_PATH + script, env={"POOL": config.pool})


def build(config: ConfigModel) -> Build:
    return Build(
        actions=[
            ActionTemplate(
                key="scrub",
                name=f"Scrub {config.pool}",
                description=f"Starts a scrub of {config.pool}: ZFS reads and verifies every "
                "block in the background, which can take hours.",
                executor=Executor.SSH,
                target_id=config.target_id,
                spec=_spec(f'{AS_ROOT}root zpool scrub -- "$POOL" && echo "Scrub started"', config),
                button=ButtonTemplate(label=f"Scrub {config.pool}", color=ButtonColor.SKY),
            )
        ],
        tiles=[TileTemplate(state_key="health", label=config.pool)],
    )


def probe(config: ConfigModel) -> Probe:
    # Prints "<health>\t<capacity>", e.g. "ONLINE\t62%".
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=_spec('zpool list -H -o health,capacity -- "$POOL"', config),
    )


_TONES = {"ONLINE": StateTone.GOOD, "DEGRADED": StateTone.WARN}


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    fields = last.split()
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0 and len(fields) == 2 and fields[1].rstrip("%").isdigit():
        health, percent = fields[0], int(fields[1].rstrip("%"))
        value, detail = health.lower(), f"{percent}% full"
        tone = _TONES.get(health, StateTone.BAD)  # FAULTED, OFFLINE, UNAVAIL, REMOVED.
        if tone == StateTone.GOOD and percent >= WARN_PERCENT:
            tone = StateTone.WARN
    elif "no such pool" in result.output:
        value, tone, detail = "not found", StateTone.BAD, f"No pool named {config.pool}"
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = last or f"zpool exited with {result.exit_code}"
    return [StateValue("health", value, tone, detail)]


FEATURE = Feature(
    id="zfs_pool",
    name="ZFS pool",
    description=f"See a ZFS pool's health and how full it is (amber from {WARN_PERCENT}%), "
    "and start a scrub.",
    icon="database",
    category="Storage",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("scrub", "Scrub", "Starts a scrub that verifies every block."),
        tile("health", "Health", "The pool's health and how full it is."),
    ],
    poll=Poll(probe=probe, parse=parse, interval_seconds=60),
)
