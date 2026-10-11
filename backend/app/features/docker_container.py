"""Start, stop, and restart one Docker container on an SSH host."""

from pydantic import BaseModel, Field

from app.features.base import ActionTemplate, ButtonTemplate, Feature, SshTargetId
from app.models import ButtonColor, Executor
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


# (key, verb, docker subcommand, description, color, confirm). The container name reaches
# the script as $CONTAINER; it is never interpolated into the script text.
_COMMANDS = [
    ("start", "Start", "start", "Starts the {} container.", ButtonColor.EMERALD, False),
    ("stop", "Stop", "stop", "Stops the {} container.", ButtonColor.RED, True),
    ("restart", "Restart", "restart", "Restarts the {} container.", ButtonColor.AMBER, False),
]


def build(config: ConfigModel) -> list[ActionTemplate]:
    return [
        ActionTemplate(
            key=key,
            name=f"{verb} {config.container}",
            description=description.format(config.container),
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=ScriptSpec(
                script=f'docker {command} "$CONTAINER"', env={"CONTAINER": config.container}
            ),
            # docker stop waits up to 10 seconds before killing the container.
            timeout_seconds=60,
            confirm=confirm,
            button=ButtonTemplate(label=f"{verb} {config.container}", color=color),
        )
        for key, verb, command, description, color, confirm in _COMMANDS
    ]


FEATURE = Feature(
    id="docker_container",
    name="Docker container",
    description="Start, stop, and restart a Docker container on an SSH host.",
    icon="container",
    category="Docker",
    ConfigModel=ConfigModel,
    build=build,
)
