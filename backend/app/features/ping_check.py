"""Show whether a host answers ping, and how fast. Runs from the runpad container."""

import re

from pydantic import BaseModel, Field

from app.features.base import Build, Feature, Poll, Probe, ProbeResult, StateValue, TileTemplate
from app.models import Executor, StateTone
from app.schemas.actions import ScriptSpec


class ConfigModel(BaseModel):
    host: str = Field(
        title="Host",
        description="Hostname or IP address, as seen from the runpad container.",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9.:-]*$",
        max_length=253,
    )


def build(config: ConfigModel) -> Build:
    return Build(actions=[], tiles=[TileTemplate(state_key="ping", label=config.host)])


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.LOCAL,
        spec=ScriptSpec(script='ping -n -c 1 -W 2 -- "$HOST"', env={"HOST": config.host}),
        timeout_seconds=10,
    )


_TIME = re.compile(r"time(=|<)([\d.]+) ?ms")


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    if result.error is not None:
        return [StateValue("ping", "unknown", StateTone.UNKNOWN, result.error)]
    if result.exit_code == 0:
        match = _TIME.search(result.output)
        less = "<" if match and match.group(1) == "<" else ""
        latency = f"{less}{float(match.group(2)):g} ms" if match else ""
        return [StateValue("ping", "up", StateTone.GOOD, latency)]
    # iputils ping exits 1 when there was no reply, 2 on other errors (such as an
    # unknown host), which it prints.
    lines = result.output.strip().splitlines()
    detail = "No reply" if result.exit_code == 1 or not lines else lines[-1]
    return [StateValue("ping", "down", StateTone.BAD, detail)]


FEATURE = Feature(
    id="ping_check",
    name="Ping check",
    description="See whether a host answers ping, and its latency.",
    icon="ping",
    category="Network",
    ConfigModel=ConfigModel,
    build=build,
    poll=Poll(probe=probe, parse=parse),
)
