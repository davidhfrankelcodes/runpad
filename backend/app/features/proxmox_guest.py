"""Start, shut down, and reboot a Proxmox VE virtual machine or container, and show whether
it runs. Commands run on the Proxmox node over SSH."""

from typing import Literal

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

# qm and pct live in /usr/sbin, which is not on a normal user's PATH.
_PATH = 'PATH="$PATH:/usr/sbin:/sbin"\n'


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Proxmox node",
        description="The SSH target of the node the guest runs on. Its user must be root, "
        "or allowed to run qm and pct with sudo without a password.",
    )
    guest_type: Literal["vm", "container"] = Field(
        default="vm",
        title="Type",
        description="vm for a QEMU virtual machine (qm), container for an LXC container (pct).",
    )
    vmid: int = Field(
        title="ID", description="The guest's numeric ID, such as 100.", ge=100, le=999_999_999
    )
    name: str = Field(
        title="Guest name",
        description="Shown on the buttons and the tile.",
        min_length=1,
        max_length=40,
    )

    def cli(self) -> str:
        return "qm" if self.guest_type == "vm" else "pct"


_COMMANDS = [
    # key, verb, description, color, confirm
    ("start", "Start", "Starts {}.", ButtonColor.EMERALD, False),
    ("shutdown", "Shut down", "Asks {} to shut down cleanly.", ButtonColor.RED, True),
    ("reboot", "Reboot", "Asks {} to restart cleanly.", ButtonColor.AMBER, False),
]


def _spec(script: str, config: ConfigModel) -> ScriptSpec:
    return ScriptSpec(
        script=f"{_PATH}{AS_ROOT}{script}", env={"CLI": config.cli(), "VMID": str(config.vmid)}
    )


def build(config: ConfigModel) -> Build:
    actions = [
        ActionTemplate(
            key=key,
            name=f"{verb} {config.name}",
            description=description.format(config.name),
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=_spec(f'root "$CLI" {key} "$VMID"', config),
            # A clean shutdown can take a while; qm waits for it.
            timeout_seconds=300,
            confirm=confirm,
            button=ButtonTemplate(label=f"{verb} {config.name}", color=color),
        )
        for key, verb, description, color, confirm in _COMMANDS
    ]
    return Build(actions=actions, tiles=[TileTemplate(state_key="status", label=config.name)])


def probe(config: ConfigModel) -> Probe:
    # Prints "status: running", "status: stopped", ...
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=_spec('root "$CLI" status "$VMID"', config),
    )


_TONES = {"running": StateTone.GOOD, "stopped": StateTone.BAD}


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0 and last.startswith("status:"):
        status = last.removeprefix("status:").strip()[:64] or "unknown"
        value, tone, detail = status, _TONES.get(status, StateTone.NEUTRAL), ""
    elif "does not exist" in result.output:
        kind = "VM" if config.guest_type == "vm" else "container"
        value, tone, detail = "not found", StateTone.BAD, f"No {kind} with ID {config.vmid}"
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = last or f"{config.cli()} exited with {result.exit_code}"
    return [StateValue("status", value, tone, detail)]


FEATURE = Feature(
    id="proxmox_guest",
    name="Proxmox guest",
    description="Start, shut down, and reboot a Proxmox VE virtual machine or container, "
    "and see whether it is running.",
    icon="server",
    category="Virtualization",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("start", "Start", "Starts the VM or container."),
        button("shutdown", "Shut down", "Asks the guest to shut down cleanly. Asks first."),
        button("reboot", "Reboot", "Asks the guest to restart cleanly."),
        tile("status", "Status", "Running, stopped, or not found."),
    ],
    poll=Poll(probe=probe, parse=parse),
)
