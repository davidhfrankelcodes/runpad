"""Wake a machine with a Wake-on-LAN magic packet, sent from an SSH host on its network."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.features.base import ActionTemplate, Build, ButtonTemplate, Feature, SshTargetId, button
from app.models import ButtonColor, Executor
from app.schemas.actions import ScriptSpec


def _normalize_mac(value: str) -> str:
    return value.replace("-", ":").lower()


Mac = Annotated[
    str,
    Field(pattern=r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$"),
    AfterValidator(_normalize_mac),
]


class ConfigModel(BaseModel):
    target_id: SshTargetId = Field(
        title="Send from",
        description="An SSH target on the same network as the machine, with python3. "
        "runpad's own container usually cannot reach that network's broadcast address.",
    )
    mac: Mac = Field(title="MAC address", description="Of the machine to wake.")
    name: str = Field(
        title="Machine name", description="Shown on the button.", min_length=1, max_length=40
    )
    broadcast: str = Field(
        default="255.255.255.255",
        title="Broadcast address",
        description="Change only if the packet must go to a specific subnet, "
        "for example 192.168.1.255.",
        pattern=r"^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$",
    )


# The address and MAC arrive as environment variables; python3 builds the packet (16
# repetitions of the MAC after six 0xff bytes) and broadcasts it on UDP port 9.
SEND = """python3 -c '
import os, socket
mac = bytes.fromhex(os.environ["MAC"].replace(":", ""))
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
s.sendto(b"\\xff" * 6 + mac * 16, (os.environ["BROADCAST"], int(os.environ["PORT"])))
print("Sent a magic packet to", os.environ["MAC"])
'"""


def build(config: ConfigModel) -> Build:
    return Build(
        actions=[
            ActionTemplate(
                key="wake",
                name=f"Wake {config.name}",
                description=f"Turns {config.name} on over the network.",
                executor=Executor.SSH,
                target_id=config.target_id,
                spec=ScriptSpec(
                    script=SEND,
                    env={"MAC": config.mac, "BROADCAST": config.broadcast, "PORT": "9"},
                ),
                button=ButtonTemplate(label=f"Wake {config.name}", color=ButtonColor.EMERALD),
            )
        ]
    )


FEATURE = Feature(
    id="wake_on_lan",
    name="Wake-on-LAN",
    description="Turn a machine on over the network, sending the packet from a host on "
    "its network.",
    icon="wake",
    category="System",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("wake", "Wake", "Turns the machine on over the network."),
    ],
)
