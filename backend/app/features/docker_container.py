"""Start, stop, and restart one Docker container on an SSH host, and show whether it runs."""

from pydantic import BaseModel, Field

from app.features.base import (
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


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target running Docker. Its user must be able to run docker "
        "without sudo (for example, by being in the docker group).",
    )
    container: str = Field(
        title="Container name",
        description="As shown by docker ps.",
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$",
    )


LOG_LINES = 200

# (key, verb, docker subcommand, description, color, confirm). The container name reaches
# the script as $CONTAINER; it is never interpolated into the script text.
_COMMANDS = [
    ("start", "Start", "start", "Starts the {} container.", ButtonColor.EMERALD, False),
    ("stop", "Stop", "stop", "Stops the {} container.", ButtonColor.RED, True),
    ("restart", "Restart", "restart", "Restarts the {} container.", ButtonColor.AMBER, False),
]


def _spec(script: str, config: ConfigModel) -> ScriptSpec:
    return ScriptSpec(script=script, env={"CONTAINER": config.container})


def build(config: ConfigModel) -> Build:
    actions = [
        ActionTemplate(
            key=key,
            name=f"{verb} {config.container}",
            description=description.format(config.container),
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=_spec(f'docker {command} "$CONTAINER"', config),
            # docker stop waits up to 10 seconds before killing the container.
            timeout_seconds=60,
            confirm=confirm,
            button=ButtonTemplate(label=f"{verb} {config.container}", color=color),
        )
        for key, verb, command, description, color, confirm in _COMMANDS
    ]
    actions.append(
        ActionTemplate(
            key="logs",
            name=f"Logs of {config.container}",
            description=f"Shows the last {LOG_LINES} lines of the {config.container} "
            "container's log.",
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=_spec(f'docker logs --tail {LOG_LINES} "$CONTAINER" 2>&1', config),
            button=ButtonTemplate(label=f"Logs of {config.container}"),
        )
    )
    return Build(actions=actions, tiles=[TileTemplate(state_key="status", label=config.container)])


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=_spec("docker inspect --format '{{.State.Status}}' \"$CONTAINER\"", config),
    )


# docker's State.Status values: created, running, paused, restarting, removing, exited, dead.
_TONES = {"running": StateTone.GOOD, "exited": StateTone.BAD, "dead": StateTone.BAD}
_LABELS = {"exited": "stopped"}


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0:
        status = result.output.strip()
        value = _LABELS.get(status, status)[:64] or "unknown"
        tone, detail = _TONES.get(status, StateTone.NEUTRAL), ""
    elif "no such object" in result.output.lower():  # Capitalized in older docker CLIs.
        value, tone, detail = "not found", StateTone.BAD, f"No container named {config.container}"
    else:
        lines = result.output.strip().splitlines()
        value, tone = "unknown", StateTone.UNKNOWN
        detail = lines[-1] if lines else f"docker exited with {result.exit_code}"
    return [StateValue(key="status", value=value, tone=tone, detail=detail)]


FEATURE = Feature(
    id="docker_container",
    name="Docker container",
    description="Start, stop, and restart a Docker container on an SSH host, see its "
    "logs, and see whether it is running.",
    icon="container",
    category="Docker",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("start", "Start", "Starts the container."),
        button("stop", "Stop", "Stops the container. Asks first."),
        button("restart", "Restart", "Restarts the container."),
        button("logs", "Logs", "Shows the last 200 lines of the container's log."),
        tile("status", "Status", "Running, stopped, or not found."),
    ],
    poll=Poll(probe=probe, parse=parse),
)
