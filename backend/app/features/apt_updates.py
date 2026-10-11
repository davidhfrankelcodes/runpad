"""Show pending package updates on a Debian or Ubuntu host, and install them."""

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


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target, running Debian or Ubuntu. Its user must be root, or "
        "allowed to run apt-get with sudo without a password.",
    )
    name: str = Field(
        title="Host name",
        description="Shown on the buttons and the tile.",
        min_length=1,
        max_length=40,
    )


# Never ask questions, and keep changed config files rather than replacing them.
_APT = (
    "root env DEBIAN_FRONTEND=noninteractive apt-get -y "
    "-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
)


def build(config: ConfigModel) -> Build:
    return Build(
        actions=[
            ActionTemplate(
                key="refresh",
                name=f"Check {config.name} for updates",
                description=f"Downloads the latest package lists on {config.name}, so the "
                "tile shows every update.",
                executor=Executor.SSH,
                target_id=config.target_id,
                spec=ScriptSpec(script=f"{AS_ROOT}{_APT} update"),
                timeout_seconds=300,
                button=ButtonTemplate(label=f"Check {config.name}", color=ButtonColor.SKY),
            ),
            ActionTemplate(
                key="upgrade",
                name=f"Update {config.name}",
                description=f"Installs every pending package update on {config.name}. "
                "Packages that need new dependencies are held back.",
                executor=Executor.SSH,
                target_id=config.target_id,
                spec=ScriptSpec(script=f"{AS_ROOT}{_APT} update && {_APT} upgrade"),
                timeout_seconds=1800,
                confirm=True,
                button=ButtonTemplate(label=f"Update {config.name}", color=ButtonColor.AMBER),
            ),
        ],
        tiles=[TileTemplate(state_key="updates", label=f"{config.name} updates")],
    )


# Simulates an upgrade from the current package lists (no root, no lock, no changes) and
# prints "updates <count> <security count> <reboot required: 0 or 1>". Exit 3: no apt-get.
SCRIPT = """command -v apt-get >/dev/null || exit 3
plan=$(apt-get -s -o Debug::NoLocking=1 upgrade 2>&1) || { printf '%s\\n' "$plan"; exit 4; }
installs=$(printf '%s\\n' "$plan" | grep '^Inst ')
reboot=0
[ -e /var/run/reboot-required ] && reboot=1
echo "updates $(printf '%s' "$installs" | grep -c .) \
$(printf '%s' "$installs" | grep -c -- '-security') $reboot"
"""


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=ScriptSpec(script=SCRIPT),
        timeout_seconds=60,
    )


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    words = last.split()
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 3:
        value, tone, detail = "no apt", StateTone.UNKNOWN, "apt-get was not found on this host"
    elif (
        result.exit_code == 0
        and len(words) == 4
        and words[0] == "updates"
        and all(w.isdigit() for w in words[1:])
    ):
        count, security, reboot = int(words[1]), int(words[2]), words[3] == "1"
        notes = []
        if security:
            notes.append(f"{security} security")
        if reboot:
            notes.append("reboot required")
        detail = " · ".join(notes)
        if count:
            value = f"{count} update{'s' if count != 1 else ''}"
            tone = StateTone.WARN
        else:
            value, tone = "up to date", StateTone.WARN if reboot else StateTone.GOOD
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = last or f"The check exited with {result.exit_code}"
    return [StateValue("updates", value, tone, detail)]


FEATURE = Feature(
    id="apt_updates",
    name="Package updates",
    description="See pending package updates on a Debian or Ubuntu host, and install them "
    "with one button.",
    icon="updates",
    category="System",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("refresh", "Check for updates", "Downloads the latest package lists."),
        button("upgrade", "Update", "Installs every pending update. Asks first."),
        tile(
            "updates",
            "Pending updates",
            "How many updates wait, how many are security fixes, and whether a reboot is needed.",
        ),
    ],
    poll=Poll(probe=probe, parse=parse, interval_seconds=600),
)
