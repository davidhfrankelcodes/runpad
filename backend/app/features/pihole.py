"""Pause and resume a Pi-hole's ad blocking, and show whether it is blocking and how much,
through its API (Pi-hole v6). Runs from the runpad container.

Pi-hole's API takes a password, not a bearer token: a script logs in (POST /api/auth), uses
the session it gets, and logs out again, since Pi-hole allows only a few sessions at once.
The password is a text Secret that reaches scripts as $PIHOLE_PASSWORD through secret_env,
so it is redacted from output and never stored in the config. Redirects are never followed,
so the password only goes to the configured Pi-hole.
"""

import json
import uuid
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from app.features.base import (
    ActionTemplate,
    Build,
    ButtonTemplate,
    Feature,
    Poll,
    Probe,
    ProbeResult,
    StateValue,
    TextSecretId,
    TileTemplate,
    button,
    tile,
)
from app.models import ButtonColor, Executor, StateTone
from app.schemas.actions import ScriptSpec, SecretEnv


class ConfigModel(BaseModel):
    url: str = Field(
        title="Pi-hole address",
        description="As seen from the runpad container, for example http://pi.hole or "
        "http://192.168.1.2. HTTPS needs a valid certificate; Pi-hole's own self-signed one "
        "is not, so use http:// for it.",
        pattern=r"^https?://[^\s/$.?#][^\s]*$",
        max_length=500,
    )
    password_secret_id: TextSecretId = Field(
        title="Password",
        description="A text secret holding the web interface password, or better an app "
        "password (Settings, Web interface / API, Configure app password).",
    )
    pause_minutes: int = Field(
        default=5,
        title="Pause for (minutes)",
        description="How long Pause turns blocking off. Pi-hole turns it back on by itself.",
        ge=1,
        le=1440,
    )


# Helpers every Pi-hole script starts with. Exit codes: 5 password rejected, 6 other HTTP
# error, 7 Pi-hole unreachable.
CLIENT = r"""
import json, os, sys, urllib.error, urllib.request

BASE = os.environ["PIHOLE_URL"].rstrip("/")
if BASE.endswith("/admin"):  # The address of the web interface, as people copy it.
    BASE = BASE[: -len("/admin")]
BASE += "/api/"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)
SID = None


def fail(message, code):
    print(message, flush=True)
    sys.exit(code)


def call(path, method="GET", body=None):
    headers = {"Content-Type": "application/json"}
    if SID:
        headers["X-FTL-SID"] = SID
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with OPENER.open(request, timeout=20) as response:
            text = response.read().decode() or "{}"
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            fail("Pi-hole redirected to %s; use that address instead"
                 % exc.headers.get("Location"), 6)
        if exc.code == 401:
            fail("Pi-hole rejected the password", 5)
        if exc.code == 429:
            fail("Pi-hole has no free API sessions; it frees them after 30 minutes", 6)
        if exc.code == 404:
            fail("No Pi-hole v6 API at " + BASE + " (Pi-hole 5 is not supported)", 6)
        fail("Pi-hole answered HTTP %d for %s" % (exc.code, BASE + path), 6)
    except (urllib.error.URLError, OSError) as exc:
        fail("Could not reach Pi-hole: %s" % getattr(exc, "reason", exc), 7)
    except ValueError:
        fail("Pi-hole sent an answer that is not JSON; is this a Pi-hole v6?", 6)


def login():
    global SID
    session = call("auth", "POST", {"password": os.environ["PIHOLE_PASSWORD"]}).get("session", {})
    if not session.get("valid"):
        fail("Pi-hole rejected the password", 5)
    SID = session.get("sid")  # None when Pi-hole has no password set.


def logout():
    if SID:
        try:
            call("auth", "DELETE")
        except SystemExit:
            pass  # The work is done; the session expires by itself.


def minutes(seconds):
    seconds = int(seconds or 0)
    return "%d min" % ((seconds + 59) // 60) if seconds >= 60 else "%d s" % seconds
"""

PAUSE = r"""
seconds = int(os.environ["PAUSE_SECONDS"])
result = call("dns/blocking", "POST", {"blocking": False, "timer": seconds})
print("Ad blocking is paused for " + minutes(result.get("timer")) + ".")
"""

RESUME = r"""
call("dns/blocking", "POST", {"blocking": True, "timer": None})
print("Ad blocking is on again.")
"""

# Prints one line: "pihole <JSON>", with the blocking status and the last 24 hours' queries.
STATUS = r"""
blocking = call("dns/blocking")
queries = call("stats/summary").get("queries", {})
print("pihole " + json.dumps({
    "blocking": blocking.get("blocking"),
    "timer": blocking.get("timer"),
    "total": queries.get("total"),
    "percent_blocked": queries.get("percent_blocked"),
}))
"""


def _spec(config: ConfigModel, main: str) -> ScriptSpec:
    body = f"login()\ntry:\n{_indent(main.strip())}\nfinally:\n    logout()\n"
    return ScriptSpec(
        script=f"python3 - <<'PY'\n{CLIENT}\n{body}PY\n",
        env={"PIHOLE_URL": config.url, "PAUSE_SECONDS": str(config.pause_minutes * 60)},
    )


def _indent(text: str) -> str:
    return "\n".join(f"    {line}" if line else "" for line in text.splitlines())


def _password(config: ConfigModel) -> list[SecretEnv]:
    secret_id: uuid.UUID = config.password_secret_id
    return [SecretEnv(name="PIHOLE_PASSWORD", secret_id=secret_id)]


def build(config: ConfigModel) -> Build:
    secrets = _password(config)
    pause = f"Pause ad blocking {config.pause_minutes} min"
    return Build(
        actions=[
            ActionTemplate(
                key="pause",
                name=pause,
                description=f"Turns Pi-hole's ad blocking off for {config.pause_minutes} "
                "minutes. It turns back on by itself.",
                executor=Executor.LOCAL,
                spec=_spec(config, PAUSE),
                secret_env=secrets,
                button=ButtonTemplate(label=pause, color=ButtonColor.AMBER),
            ),
            ActionTemplate(
                key="resume",
                name="Resume ad blocking",
                description="Turns Pi-hole's ad blocking back on now.",
                executor=Executor.LOCAL,
                spec=_spec(config, RESUME),
                secret_env=secrets,
                button=ButtonTemplate(label="Resume ad blocking", color=ButtonColor.EMERALD),
            ),
        ],
        # Its host name (pi.hole), which tells two Pi-holes apart; the kind line says Pi-hole.
        tiles=[
            TileTemplate(state_key="blocking", label=urlsplit(config.url).hostname or "Pi-hole")
        ],
    )


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.LOCAL,
        spec=_spec(config, STATUS),
        secret_env=_password(config),
        timeout_seconds=30,
    )


def _failure(result: ProbeResult) -> str:
    lines = result.output.strip().splitlines()
    return lines[-1] if lines else f"The check exited with {result.exit_code}"


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    if result.error is not None:
        return [StateValue("blocking", "unknown", StateTone.UNKNOWN, result.error)]
    if result.exit_code == 7:
        return [StateValue("blocking", "down", StateTone.BAD, _failure(result))]
    if result.exit_code != 0 or not last.startswith("pihole "):
        return [StateValue("blocking", "unknown", StateTone.UNKNOWN, _failure(result))]
    try:
        info = json.loads(last.removeprefix("pihole "))
    except ValueError:
        return [StateValue("blocking", "unknown", StateTone.UNKNOWN, "Unexpected answer")]
    percent, total = info.get("percent_blocked"), info.get("total")
    stats = (
        f"{percent:.1f}% of {total:,} queries blocked (24 h)"
        if isinstance(percent, int | float) and isinstance(total, int)
        else ""
    )
    status = info.get("blocking")
    if status == "enabled":
        return [StateValue("blocking", "blocking", StateTone.GOOD, stats)]
    if status == "disabled":
        timer = info.get("timer")
        back = (
            f"Back on in {_minutes(timer)}"
            if isinstance(timer, int | float) and timer > 0
            else "Off until turned on"
        )
        return [StateValue("blocking", "paused", StateTone.WARN, back)]
    return [StateValue("blocking", str(status or "unknown"), StateTone.BAD, stats)]


def _minutes(seconds: float) -> str:
    whole = int(seconds)
    return f"{(whole + 59) // 60} min" if whole >= 60 else f"{whole} s"


FEATURE = Feature(
    id="pihole",
    name="Pi-hole",
    description="Pause and resume a Pi-hole's ad blocking, and see whether it is blocking "
    "and how much. Pi-hole 6 and later.",
    icon="shield",
    category="Network",
    ConfigModel=ConfigModel,
    build=build,
    items=[
        button("pause", "Pause blocking", "Turns ad blocking off for a few minutes."),
        button("resume", "Resume blocking", "Turns ad blocking back on now."),
        tile("blocking", "Status", "Blocking or paused, and how much it blocked in 24 hours."),
    ],
    poll=Poll(probe=probe, parse=parse, interval_seconds=60),
)
