"""Start, stop, and restart a systemd service on an SSH host, and show whether it is active."""

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
        description="The SSH target. Its user must be root, or allowed to run systemctl and "
        "journalctl with sudo without a password.",
    )
    unit: str = Field(
        title="Service",
        description="The unit name, for example nginx or nginx.service.",
        pattern=r"^[A-Za-z0-9@_:.][A-Za-z0-9@_:.-]*$",
        max_length=255,
    )


LOG_LINES = 200

_COMMANDS = [
    ("start", "Start", "Starts the {} service.", ButtonColor.EMERALD, False),
    ("stop", "Stop", "Stops the {} service.", ButtonColor.RED, True),
    ("restart", "Restart", "Restarts the {} service.", ButtonColor.AMBER, False),
]


def _spec(script: str, config: ConfigModel) -> ScriptSpec:
    return ScriptSpec(script=script, env={"UNIT": config.unit})


def build(config: ConfigModel) -> Build:
    actions = [
        ActionTemplate(
            key=key,
            name=f"{verb} {config.unit}",
            description=description.format(config.unit),
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=_spec(f'{AS_ROOT}root systemctl {key} "$UNIT"', config),
            timeout_seconds=120,
            confirm=confirm,
            button=ButtonTemplate(label=f"{verb} {config.unit}", color=color),
        )
        for key, verb, description, color, confirm in _COMMANDS
    ]
    actions.append(
        ActionTemplate(
            key="logs",
            name=f"Logs of {config.unit}",
            description=f"Shows the last {LOG_LINES} lines of the {config.unit} service's log.",
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=_spec(f'{AS_ROOT}root journalctl --no-pager -n {LOG_LINES} -u "$UNIT"', config),
            button=ButtonTemplate(label=f"Logs of {config.unit}"),
        )
    )
    return Build(actions=actions, tiles=[TileTemplate(state_key="active", label=config.unit)])


def probe(config: ConfigModel) -> Probe:
    # Reading state needs no root. Prints "<LoadState> <ActiveState>", e.g. "loaded active".
    script = (
        'echo "$(systemctl show -p LoadState --value -- "$UNIT")'
        ' $(systemctl show -p ActiveState --value -- "$UNIT")"'
    )
    return Probe(executor=Executor.SSH, target_id=config.target_id, spec=_spec(script, config))


_TONES = {"active": StateTone.GOOD, "inactive": StateTone.BAD, "failed": StateTone.BAD}


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    words = lines[-1].split() if lines else []
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0 and len(words) == 2 and words[0] == "not-found":
        value, tone, detail = "not found", StateTone.BAD, f"No unit named {config.unit}"
    elif result.exit_code == 0 and len(words) == 2:
        value, tone, detail = words[1], _TONES.get(words[1], StateTone.NEUTRAL), ""
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = lines[-1] if lines else f"systemctl exited with {result.exit_code}"
    return [StateValue(key="active", value=value, tone=tone, detail=detail)]


FEATURE = Feature(
    id="systemd_service",
    name="systemd service",
    description="Start, stop, and restart a systemd service on an SSH host, see its logs, "
    "and see whether it is active.",
    icon="service",
    category="System",
    ConfigModel=ConfigModel,
    build=build,
    poll=Poll(probe=probe, parse=parse),
)
