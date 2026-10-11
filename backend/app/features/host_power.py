"""Reboot or shut down an SSH host, and show whether it is reachable."""

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
)
from app.models import ButtonColor, Executor, StateTone
from app.schemas.actions import ScriptSpec


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target, running systemd. Its user must be root, or allowed to "
        "run systemd-run with sudo without a password.",
    )
    name: str = Field(
        title="Host name",
        description="Shown on the buttons and the tile.",
        min_length=1,
        max_length=40,
    )


# The power change is scheduled through systemd a few seconds out, so the Run can finish
# and report success before the connection goes away (and so it is not part of the Run's
# process group, which is killed when the script ends).
def _schedule(command: str) -> str:
    return (
        f"{AS_ROOT}root systemd-run --quiet --on-active=3 "
        f"--timer-property=AccuracySec=100ms systemctl {command}\n"
        f'echo "{command} in 3 seconds"'
    )


def build(config: ConfigModel) -> Build:
    commands = [
        ("reboot", "Reboot", "reboot", "Restarts {}."),
        ("shutdown", "Shut down", "poweroff", "Turns {} off."),
    ]
    actions = [
        ActionTemplate(
            key=key,
            name=f"{verb} {config.name}",
            description=description.format(config.name),
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=ScriptSpec(script=_schedule(command)),
            confirm=True,  # Security rule: reboot and shut down always ask first.
            button=ButtonTemplate(label=f"{verb} {config.name}", color=ButtonColor.RED),
        )
        for key, verb, command, description in commands
    ]
    return Build(actions=actions, tiles=[TileTemplate(state_key="reachable", label=config.name)])


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=ScriptSpec(script="cat /proc/uptime"),
    )


def _uptime(proc_uptime: str) -> str:
    """ "up 3 d 4 h" from /proc/uptime ("<seconds> <idle seconds>"), or "" if not Linux."""
    try:
        seconds = float(proc_uptime.split()[0])
    except (IndexError, ValueError):
        return ""
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    if days:
        return f"up {days} d {hours} h"
    if hours:
        return f"up {hours} h {rest // 60} min"
    return f"up {rest // 60} min"


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    if result.error is not None:
        return [StateValue("reachable", "unreachable", StateTone.BAD, result.error)]
    detail = _uptime(result.output) if result.exit_code == 0 else ""
    return [StateValue("reachable", "reachable", StateTone.GOOD, detail)]


FEATURE = Feature(
    id="host_power",
    name="Host power",
    description="Reboot or shut down a host over SSH, and see whether it is reachable.",
    icon="power",
    category="System",
    ConfigModel=ConfigModel,
    build=build,
    poll=Poll(probe=probe, parse=parse),
)
