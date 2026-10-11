"""Show whether a TCP port accepts connections. Runs from the runpad container."""

from pydantic import BaseModel, Field

from app.features.base import (
    Build,
    Feature,
    Poll,
    Probe,
    ProbeResult,
    StateValue,
    TileTemplate,
    tile,
)
from app.models import Executor, StateTone
from app.schemas.actions import ScriptSpec


class ConfigModel(BaseModel):
    host: str = Field(
        title="Host",
        description="Hostname or IP address, as seen from the runpad container.",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9.:-]*$",
        max_length=253,
    )
    port: int = Field(title="Port", description="For example 22, 443, or 5432.", ge=1, le=65535)


def build(config: ConfigModel) -> Build:
    return Build(
        actions=[], tiles=[TileTemplate(state_key="port", label=f"{config.host}:{config.port}")]
    )


# Prints "open <milliseconds>", or "closed <reason>".
SCRIPT = """python3 -c '
import os, socket, time
start = time.monotonic()
try:
    socket.create_connection((os.environ["HOST"], int(os.environ["PORT"])), timeout=5).close()
except OSError as exc:
    print("closed", exc.strerror or exc)
    raise SystemExit(1)
print("open", round((time.monotonic() - start) * 1000))
'"""


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.LOCAL,
        spec=ScriptSpec(script=SCRIPT, env={"HOST": config.host, "PORT": str(config.port)}),
        timeout_seconds=10,
    )


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    words = last.split()
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0 and len(words) == 2 and words[0] == "open":
        value, tone, detail = "open", StateTone.GOOD, f"{words[1]} ms"
    elif result.exit_code == 1 and words[:1] == ["closed"]:
        value, tone, detail = "closed", StateTone.BAD, last.removeprefix("closed ")
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = last or f"The check exited with {result.exit_code}"
    return [StateValue("port", value, tone, detail)]


FEATURE = Feature(
    id="port_check",
    name="Port check",
    description="See whether a TCP port accepts connections, such as a database or SSH.",
    icon="port",
    category="Network",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        tile("port", "Port", "Open or closed."),
    ],
    poll=Poll(probe=probe, parse=parse),
)
