"""Show whether a web page answers, with its HTTP status and response time. Runs from the
runpad container."""

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
    url: str = Field(
        title="URL",
        description="An http:// or https:// address, as seen from the runpad container. "
        "Redirects are followed; HTTPS certificates must be valid.",
        pattern=r"^https?://[^\s/$.?#][^\s]*$",
        max_length=2000,
    )
    name: str = Field(
        title="Site name", description="Shown on the tile.", min_length=1, max_length=40
    )


def build(config: ConfigModel) -> Build:
    return Build(actions=[], tiles=[TileTemplate(state_key="site", label=config.name)])


# Prints "status <code> <milliseconds>", or "error <reason>" when there was no HTTP answer.
# 4xx and 5xx answers raise HTTPError, which still carries the status.
SCRIPT = """python3 -c '
import os, time, urllib.error, urllib.request
request = urllib.request.Request(os.environ["URL"], headers={"User-Agent": "runpad"})
start = time.monotonic()
try:
    with urllib.request.urlopen(request, timeout=10) as response:
        status = response.status
except urllib.error.HTTPError as exc:
    status = exc.code
except Exception as exc:
    print("error", getattr(exc, "reason", None) or exc)
    raise SystemExit(2)
print("status", status, round((time.monotonic() - start) * 1000))
'"""


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.LOCAL,
        spec=ScriptSpec(script=SCRIPT, env={"URL": config.url}),
        timeout_seconds=15,
    )


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    words = lines[-1].split() if lines else []
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0 and len(words) == 3 and words[0] == "status":
        status, ms = int(words[1]), words[2]
        ok = 200 <= status < 400
        value = "up" if ok else "error"
        tone, detail = (StateTone.GOOD if ok else StateTone.BAD), f"HTTP {status} · {ms} ms"
    elif words[:1] == ["error"]:
        value, tone, detail = "down", StateTone.BAD, lines[-1].removeprefix("error ")
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = lines[-1] if lines else f"The check exited with {result.exit_code}"
    return [StateValue("site", value, tone, detail)]


FEATURE = Feature(
    id="website_check",
    name="Website check",
    description="See whether a web page answers, with its HTTP status and response time.",
    icon="website",
    category="Network",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        tile("site", "Website", "Up or down, with the HTTP status and response time."),
    ],
    poll=Poll(probe=probe, parse=parse, interval_seconds=60),
)
