"""Start, shut down, and reboot a libvirt (KVM/QEMU) virtual machine over SSH, and show
whether it runs."""

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

# The system instance, where virt-manager and most setups keep their VMs.
_VIRSH = "virsh -c qemu:///system"


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Host",
        description="The SSH target running libvirt. Its user must be in the libvirt group "
        "(or be root).",
    )
    domain: str = Field(
        title="VM name",
        description="As shown by virsh list --all.",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$",
    )


_COMMANDS = [
    # key, verb, description, color, confirm
    ("start", "Start", "Starts the {} VM.", ButtonColor.EMERALD, False),
    ("shutdown", "Shut down", "Asks the {} VM to shut down cleanly.", ButtonColor.RED, True),
    ("reboot", "Reboot", "Asks the {} VM to restart cleanly.", ButtonColor.AMBER, False),
]


def _spec(script: str, config: ConfigModel) -> ScriptSpec:
    return ScriptSpec(script=script, env={"DOMAIN": config.domain})


def build(config: ConfigModel) -> Build:
    actions = [
        ActionTemplate(
            key=key,
            name=f"{verb} {config.domain}",
            description=description.format(config.domain),
            executor=Executor.SSH,
            target_id=config.target_id,
            spec=_spec(f'{_VIRSH} {key} "$DOMAIN"', config),
            timeout_seconds=60,
            confirm=confirm,
            button=ButtonTemplate(label=f"{verb} {config.domain}", color=color),
        )
        for key, verb, description, color, confirm in _COMMANDS
    ]
    return Build(actions=actions, tiles=[TileTemplate(state_key="status", label=config.domain)])


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.SSH,
        target_id=config.target_id,
        spec=_spec(f'{_VIRSH} domstate "$DOMAIN"', config),
    )


# virsh domstate: running, idle, paused, in shutdown, shut off, crashed, pmsuspended.
_TONES = {"running": StateTone.GOOD, "stopped": StateTone.BAD, "crashed": StateTone.BAD}
_LABELS = {"shut off": "stopped", "in shutdown": "shutting down"}


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = [line for line in result.output.strip().splitlines() if line.strip()]
    last = lines[-1] if lines else ""
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0 and last:
        state = last.strip()
        value = _LABELS.get(state, state)[:64]
        tone, detail = _TONES.get(value, StateTone.NEUTRAL), ""
    elif "failed to get domain" in result.output.lower():
        value, tone, detail = "not found", StateTone.BAD, f"No VM named {config.domain}"
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = last or f"virsh exited with {result.exit_code}"
    return [StateValue("status", value, tone, detail)]


FEATURE = Feature(
    id="libvirt_vm",
    name="libvirt VM",
    description="Start, shut down, and reboot a KVM/QEMU virtual machine managed by "
    "libvirt, and see whether it is running.",
    icon="monitor",
    category="Virtualization",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("start", "Start", "Starts the VM."),
        button("shutdown", "Shut down", "Asks the VM to shut down cleanly. Asks first."),
        button("reboot", "Reboot", "Asks the VM to restart cleanly."),
        tile("status", "Status", "Running, stopped, paused, or not found."),
    ],
    poll=Poll(probe=probe, parse=parse),
)
