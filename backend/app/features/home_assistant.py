"""Turn a Home Assistant entity on and off, and show its state, through Home Assistant's
REST API."""

import json

from pydantic import BaseModel, Field

from app.features.base import (
    ActionTemplate,
    Build,
    ButtonTemplate,
    Feature,
    HttpTargetId,
    Poll,
    Probe,
    ProbeResult,
    StateValue,
    TileTemplate,
    button,
    tile,
)
from app.models import ButtonColor, Executor, StateTone
from app.schemas.actions import HttpSpec

# Domains whose entities can be switched on and off. Scenes and scripts get one button that
# runs them; anything else (sensors, ...) only gets a tile.
SWITCHABLE = {
    "automation",
    "climate",
    "fan",
    "humidifier",
    "input_boolean",
    "light",
    "media_player",
    "siren",
    "switch",
}
RUNNABLE = {"scene", "script"}


class ConfigModel(BaseModel):
    target_id: HttpTargetId = Field(
        title="Home Assistant",
        description="An HTTP target with Home Assistant's address (e.g. "
        "http://homeassistant.local:8123) and a long-lived access token as its bearer token.",
    )
    entity_id: str = Field(
        title="Entity ID",
        description="For example light.kitchen or sensor.outside_temperature. Lights, "
        "switches, fans and the like get on, off, and toggle buttons; scenes and scripts get "
        "one button; other entities only get a tile.",
        pattern=r"^[a-z_]+\.[a-z0-9_]+$",
        max_length=255,
    )
    name: str = Field(
        title="Name", description="Shown on the buttons and the tile.", min_length=1, max_length=40
    )

    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0]


def _service(
    key: str, label: str, service: str, description: str, color: ButtonColor, config: ConfigModel
) -> ActionTemplate:
    return ActionTemplate(
        key=key,
        name=f"{label} {config.name}",
        description=description,
        executor=Executor.HTTP,
        target_id=config.target_id,
        spec=HttpSpec(
            method="POST",
            path=f"api/services/{service}",
            body={"entity_id": config.entity_id},
        ),
        button=ButtonTemplate(label=f"{label} {config.name}", color=color),
    )


def build(config: ConfigModel) -> Build:
    name, domain = config.name, config.domain()
    if domain in SWITCHABLE:
        actions = [
            _service(
                "on",
                "Turn on",
                "homeassistant/turn_on",
                f"Turns {name} on.",
                ButtonColor.EMERALD,
                config,
            ),
            _service(
                "off",
                "Turn off",
                "homeassistant/turn_off",
                f"Turns {name} off.",
                ButtonColor.SLATE,
                config,
            ),
            _service(
                "toggle",
                "Toggle",
                "homeassistant/toggle",
                f"Turns {name} on if it is off, and off if it is on.",
                ButtonColor.SKY,
                config,
            ),
        ]
    elif domain in RUNNABLE:
        verb = "Activate" if domain == "scene" else "Run"
        actions = [
            _service(
                "run",
                verb,
                f"{domain}/turn_on",
                f"{verb}s {name} in Home Assistant.",
                ButtonColor.VIOLET,
                config,
            )
        ]
    else:
        actions = []
    # A scene's state is only when it last ran, so it gets no tile.
    tiles = [] if domain == "scene" else [TileTemplate(state_key="state", label=name)]
    return Build(actions=actions, tiles=tiles)


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.HTTP,
        target_id=config.target_id,
        spec=HttpSpec(method="GET", path=f"api/states/{config.entity_id}"),
    )


_TONES = {
    "on": StateTone.GOOD,
    "home": StateTone.GOOD,
    "playing": StateTone.GOOD,
    "off": StateTone.NEUTRAL,
    "unavailable": StateTone.UNKNOWN,
    "unknown": StateTone.UNKNOWN,
}


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    # The HTTP executor's output is the status line, then the body.
    status_line, _, body = result.output.partition("\n")
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 404:
        value, tone, detail = "not found", StateTone.BAD, f"No entity {config.entity_id}"
    elif result.exit_code in (401, 403):
        value, tone, detail = "unknown", StateTone.UNKNOWN, "Home Assistant rejected the token"
    elif result.exit_code != 0:
        value, tone, detail = "unknown", StateTone.UNKNOWN, status_line.strip()
    else:
        try:
            entity = json.loads(body)
            state = str(entity["state"])
            unit = entity.get("attributes", {}).get("unit_of_measurement")
        except (ValueError, KeyError, TypeError, AttributeError):
            state, unit = "", None
        if not state:
            value, tone, detail = (
                "unknown",
                StateTone.UNKNOWN,
                "Unexpected answer from Home Assistant",
            )
        else:
            value = f"{state} {unit}"[:64] if unit else state[:64]
            tone, detail = _TONES.get(state, StateTone.NEUTRAL), ""
    return [StateValue("state", value, tone, detail)]


FEATURE = Feature(
    id="home_assistant",
    name="Home Assistant entity",
    description="Turn a light, switch, or other Home Assistant entity on and off, run "
    "scenes and scripts, and see an entity's state.",
    icon="home",
    category="Smart home",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("on", "Turn on", "For lights, switches, fans, and the like."),
        button("off", "Turn off", "For lights, switches, fans, and the like."),
        button("toggle", "Toggle", "Turns it on if off, off if on."),
        button("run", "Run scene or script", "Activates a scene or runs a script."),
        tile("state", "State", "The entity's state, such as on, off, or 21.5 °C."),
    ],
    poll=Poll(probe=probe, parse=parse),
)
