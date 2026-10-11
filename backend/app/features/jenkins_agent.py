"""Show whether a Jenkins agent (node) is online and busy, and take it offline or bring it
back, for example before maintenance on the machine it runs on."""

import json

from pydantic import Field

from app.features.base import (
    ActionTemplate,
    Build,
    ButtonTemplate,
    Feature,
    Poll,
    Probe,
    ProbeResult,
    StateValue,
    TileTemplate,
)
from app.features.jenkins import JenkinsConnection, failure_detail, jenkins_spec, token_env
from app.models import ButtonColor, Executor, StateTone
from app.schemas.actions import ScriptSpec


class ConfigModel(JenkinsConnection):
    node: str = Field(
        title="Agent name",
        description="As listed under Manage Jenkins, Nodes. The controller itself is (built-in).",
        pattern=r"^[^/\x00-\x1f]{1,100}$",
    )


_NODE = 'node = "computer/" + urllib.parse.quote(os.environ["NODE"], safe="") + "/"\n'

# Prints one line: "node <JSON>".
STATUS = (
    _NODE
    + r"""
info = get_json(node, "offline,temporarilyOffline,idle,offlineCauseReason,numExecutors")
print("node " + json.dumps(info))
"""
)

TAKE_OFFLINE = (
    _NODE
    + r"""
info = get_json(node, "offline,temporarilyOffline")
if info.get("offline"):
    print(os.environ["NODE"] + " is already offline.")
    sys.exit(0)
call(node + "toggleOffline", "POST", urllib.parse.urlencode(
    {"offlineMessage": "Taken offline from runpad"}).encode())
print(os.environ["NODE"] + " is offline: it finishes running builds but takes no new ones.")
"""
)

BRING_ONLINE = (
    _NODE
    + r"""
info = get_json(node, "offline,temporarilyOffline")
if info.get("temporarilyOffline"):
    call(node + "toggleOffline", "POST", b"")
    print(os.environ["NODE"] + " is back online.")
elif info.get("offline"):
    call(node + "launchSlaveAgent", "POST", b"")
    print("Asked Jenkins to reconnect " + os.environ["NODE"] + ".")
else:
    print(os.environ["NODE"] + " is already online.")
"""
)


def _spec(config: ConfigModel, main: str) -> ScriptSpec:
    return jenkins_spec(config, main, {"NODE": config.node})


def build(config: ConfigModel) -> Build:
    secrets = token_env(config)
    return Build(
        actions=[
            ActionTemplate(
                key="offline",
                name=f"Take {config.node} offline",
                description=f"Stops Jenkins from giving {config.node} new builds. Builds "
                "already running there finish.",
                executor=Executor.LOCAL,
                spec=_spec(config, TAKE_OFFLINE),
                secret_env=secrets,
                confirm=True,
                button=ButtonTemplate(label=f"Take {config.node} offline", color=ButtonColor.AMBER),
            ),
            ActionTemplate(
                key="online",
                name=f"Bring {config.node} online",
                description=f"Lets Jenkins give {config.node} builds again, reconnecting it "
                "if it was disconnected.",
                executor=Executor.LOCAL,
                spec=_spec(config, BRING_ONLINE),
                secret_env=secrets,
                button=ButtonTemplate(
                    label=f"Bring {config.node} online", color=ButtonColor.EMERALD
                ),
            ),
        ],
        tiles=[TileTemplate(state_key="agent", label=config.node)],
    )


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.LOCAL,
        spec=_spec(config, STATUS),
        secret_env=token_env(config),
        timeout_seconds=40,
    )


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    if result.error is not None:
        return [StateValue("agent", "unknown", StateTone.UNKNOWN, result.error)]
    if result.exit_code == 4:
        detail = f"No agent named {config.node}"
        return [StateValue("agent", "not found", StateTone.BAD, detail)]
    if result.exit_code != 0 or not last.startswith("node "):
        detail = failure_detail(result.output, result.exit_code)
        return [StateValue("agent", "unknown", StateTone.UNKNOWN, detail)]
    try:
        info = json.loads(last.removeprefix("node "))
    except ValueError:
        return [StateValue("agent", "unknown", StateTone.UNKNOWN, "Unexpected answer")]
    if info.get("offline"):
        reason = str(info.get("offlineCauseReason") or "")
        if info.get("temporarilyOffline"):
            return [StateValue("agent", "paused", StateTone.WARN, reason or "Taken offline")]
        return [StateValue("agent", "offline", StateTone.BAD, reason or "Disconnected")]
    executors = info.get("numExecutors")
    detail = f"{executors} executor{'s' if executors != 1 else ''}" if executors else ""
    value = "idle" if info.get("idle") else "busy"
    return [StateValue("agent", value, StateTone.GOOD, detail)]


FEATURE = Feature(
    id="jenkins_agent",
    name="Jenkins agent",
    description="See whether a Jenkins agent is online and busy, and take it offline or "
    "bring it back.",
    icon="agent",
    category="CI/CD",
    ConfigModel=ConfigModel,
    build=build,
    poll=Poll(probe=probe, parse=parse, interval_seconds=60),
)
