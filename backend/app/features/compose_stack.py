"""Bring a Docker Compose project up or down, or pull and recreate it, on an SSH host."""

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
)
from app.models import ButtonColor, Executor, StateTone
from app.schemas.actions import ScriptSpec


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target running Docker. Its user must be able to run docker "
        "without sudo (for example, by being in the docker group).",
    )
    project_dir: str = Field(
        title="Project directory",
        description="Absolute path of the directory holding compose.yaml.",
        pattern=r"^/[^\x00\n]*$",
        max_length=255,
    )
    name: str = Field(
        title="Stack name",
        description="Shown on the buttons and the tile.",
        min_length=1,
        max_length=40,
    )


_CD = 'cd "$PROJECT_DIR" || exit 3\n'
_COMMANDS = [
    # key, verb, script, description, color, confirm, timeout
    (
        "up",
        "Start",
        "docker compose up -d",
        "Starts the {} stack.",
        ButtonColor.EMERALD,
        False,
        300,
    ),
    ("down", "Stop", "docker compose down", "Stops the {} stack.", ButtonColor.RED, True, 300),
    (
        "update",
        "Update",
        "docker compose pull && docker compose up -d",
        "Pulls new images for the {} stack and recreates what changed.",
        ButtonColor.SKY,
        False,
        900,
    ),
]


def _spec(script: str, config: ConfigModel) -> ScriptSpec:
    return ScriptSpec(script=_CD + script, env={"PROJECT_DIR": config.project_dir})


def build(config: ConfigModel) -> Build:
    actions = [
        ActionTemplate(
            key=key,
            name=f"{verb} {config.name}",
            description=description.format(config.name),
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=_spec(script, config),
            timeout_seconds=timeout,
            confirm=confirm,
            button=ButtonTemplate(label=f"{verb} {config.name}", color=color),
        )
        for key, verb, script, description, color, confirm, timeout in _COMMANDS
    ]
    return Build(actions=actions, tiles=[TileTemplate(state_key="services", label=config.name)])


# Prints "<running> <total>": services with a running container, and services defined.
_PROBE = _CD + (
    "running=$(docker compose ps --services --status running) || exit 4\n"
    "total=$(docker compose config --services) || exit 4\n"
    'echo "$(printf "%s" "$running" | grep -c .) $(printf "%s" "$total" | grep -c .)"\n'
)


def probe(config: ConfigModel) -> Probe:
    return Probe(executor=Executor.SSH, target_id=config.target_id, spec=_spec(_PROBE, config))


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 3:
        value, tone, detail = "not found", StateTone.BAD, f"No directory {config.project_dir}"
    elif (
        result.exit_code == 0
        and len(counts := last.split()) == 2
        and all(c.isdigit() for c in counts)
    ):
        running, total = int(counts[0]), int(counts[1])
        value, detail = f"{running}/{total} up", ""
        if total and running == total:
            tone = StateTone.GOOD
        elif running == 0:
            tone = StateTone.BAD
        else:
            tone = StateTone.NEUTRAL
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = last or f"docker compose exited with {result.exit_code}"
    return [StateValue(key="services", value=value, tone=tone, detail=detail)]


FEATURE = Feature(
    id="compose_stack",
    name="Docker Compose stack",
    description="Start, stop, and update a Docker Compose project on an SSH host, and see "
    "how many of its services are up.",
    icon="stack",
    category="Docker",
    ConfigModel=ConfigModel,
    build=build,
    poll=Poll(probe=probe, parse=parse),
)
