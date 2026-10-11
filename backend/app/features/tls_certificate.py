"""Show how long a server's TLS certificate stays valid. Runs from the runpad container."""

import time
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.features.base import Build, Feature, Poll, Probe, ProbeResult, StateValue, TileTemplate
from app.models import Executor, StateTone
from app.schemas.actions import ScriptSpec

WARN_DAYS = 14


class ConfigModel(BaseModel):
    host: str = Field(
        title="Host",
        description="The name on the certificate, for example example.com.",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9.-]*$",
        max_length=253,
    )
    port: int = Field(default=443, title="Port", ge=1, le=65535)


def build(config: ConfigModel) -> Build:
    label = config.host if config.port == 443 else f"{config.host}:{config.port}"
    return Build(actions=[], tiles=[TileTemplate(state_key="certificate", label=label)])


# Prints "expires <unix time>" for a certificate that verifies for the host, "invalid
# <reason>" for one that does not (expired, self-signed, wrong name), or "error <reason>".
SCRIPT = """python3 -c '
import os, socket, ssl
host, port = os.environ["HOST"], int(os.environ["PORT"])
try:
    with socket.create_connection((host, port), timeout=10) as raw:
        with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as tls:
            cert = tls.getpeercert()
except ssl.SSLCertVerificationError as exc:
    print("invalid", exc.verify_message)
    raise SystemExit(3)
except (OSError, ssl.SSLError) as exc:
    print("error", exc.strerror or exc)
    raise SystemExit(2)
print("expires", int(ssl.cert_time_to_seconds(cert["notAfter"])))
'"""


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.LOCAL,
        spec=ScriptSpec(script=SCRIPT, env={"HOST": config.host, "PORT": str(config.port)}),
        timeout_seconds=20,
    )


def parse(config: ConfigModel, result: ProbeResult, now: float | None = None) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    words = last.split()
    if result.error is not None:
        value, tone, detail = "unknown", StateTone.UNKNOWN, result.error
    elif result.exit_code == 0 and len(words) == 2 and words[0] == "expires":
        expires = int(words[1])
        days = int((expires - (time.time() if now is None else now)) // 86400)
        value = "expires today" if days < 1 else f"{days} day{'s' if days != 1 else ''} left"
        tone = StateTone.GOOD if days >= WARN_DAYS else StateTone.WARN
        detail = f"Valid until {datetime.fromtimestamp(expires, UTC):%Y-%m-%d}"
    elif result.exit_code == 3 and words[:1] == ["invalid"]:
        value, tone, detail = "invalid", StateTone.BAD, last.removeprefix("invalid ")
    elif words[:1] == ["error"]:
        value, tone, detail = "unreachable", StateTone.BAD, last.removeprefix("error ")
    else:
        value, tone = "unknown", StateTone.UNKNOWN
        detail = last or f"The check exited with {result.exit_code}"
    return [StateValue("certificate", value, tone, detail)]


FEATURE = Feature(
    id="tls_certificate",
    name="TLS certificate",
    description=f"See how many days a site's certificate has left. Turns amber "
    f"{WARN_DAYS} days before it expires.",
    icon="certificate",
    category="Network",
    ConfigModel=ConfigModel,
    build=build,
    poll=Poll(probe=probe, parse=parse, interval_seconds=3600),
)
