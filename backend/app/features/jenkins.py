"""Shared by the Jenkins features: the connection settings, and a small Python client that
their scripts run in the runpad container.

Jenkins authenticates API calls with a user name and an API token (HTTP Basic). The token is
a text Secret, picked in the setup form, that reaches scripts as $JENKINS_TOKEN through
secret_env, so it is redacted from output and never stored in the config. Redirects are never
followed, so the credentials only go to the configured Jenkins.
"""

import uuid

from pydantic import BaseModel, Field

from app.features.base import TextSecretId
from app.schemas.actions import ScriptSpec, SecretEnv


class JenkinsConnection(BaseModel):
    url: str = Field(
        title="Jenkins URL",
        description="Its address as seen from the runpad container, for example "
        "http://jenkins.lan:8080.",
        pattern=r"^https?://[^\s/$.?#][^\s]*$",
        max_length=500,
    )
    username: str = Field(
        title="User name",
        description="The Jenkins user the API token belongs to.",
        min_length=1,
        max_length=100,
        pattern=r"^[^\s:]+$",
    )
    token_secret_id: TextSecretId = Field(
        title="API token",
        description="A text secret holding the user's API token (in Jenkins: your user, "
        "Security, API Token, Add new token). The user needs permission for what the buttons "
        "do.",
    )


# Helpers every Jenkins script starts with. Exit codes: 4 not found, 5 credentials rejected,
# 6 other HTTP error, 7 Jenkins unreachable.
CLIENT = r'''
import base64, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

BASE = os.environ["JENKINS_URL"].rstrip("/") + "/"
AUTH = "Basic " + base64.b64encode(
    (os.environ["JENKINS_USER"] + ":" + os.environ["JENKINS_TOKEN"]).encode()
).decode()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Answered as an HTTPError, which call() accepts for 3xx.


OPENER = urllib.request.build_opener(NoRedirect)


def fail(message, code):
    print(message, flush=True)
    sys.exit(code)


def call(path, method="GET", data=None):
    request = urllib.request.Request(
        BASE + path, data=data, method=method, headers={"Authorization": AUTH}
    )
    if data is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        return OPENER.open(request, timeout=30)
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            return exc  # Jenkins redirects after most POSTs; the action was taken.
        if exc.code == 404:
            page = path.split("?")[0]
            page = page[: -len("api/json")] if page.endswith("api/json") else page
            fail("Jenkins has nothing at " + BASE + page, 4)
        if exc.code in (401, 403):
            fail("Jenkins rejected the user name or API token, or the user lacks "
                 "permission (HTTP %d)" % exc.code, 5)
        fail("Jenkins answered HTTP %d for %s" % (exc.code, BASE + path), 6)
    except (urllib.error.URLError, OSError) as exc:
        fail("Could not reach Jenkins: %s" % getattr(exc, "reason", exc), 7)


def get_json(path, tree=None):
    query = "?tree=" + urllib.parse.quote(tree, safe="[],") if tree else ""
    return json.load(call(path + "api/json" + query))


# Jenkins hides "console notes" (links, timestamps) in its log as ESC[8mha:...ESC[0m.
NOTE_START, NOTE_END = "\x1b[8mha:", "\x1b[0m"
NOTES = re.compile(re.escape(NOTE_START) + ".*?" + re.escape(NOTE_END), re.S)


class LogText:
    """Strips console notes from log text that arrives in chunks, holding back a note that
    a chunk splits until the rest arrives."""

    def __init__(self):
        self.pending = ""

    def feed(self, chunk):
        text, self.pending = self.pending + chunk, ""
        start = text.rfind(NOTE_START)
        if start != -1 and text.find(NOTE_END, start) == -1:
            text, self.pending = text[:start], text[start:]
        return NOTES.sub("", text)

    def flush(self):
        text, self.pending = self.pending, ""
        return NOTES.sub("", text)


def job_path(name):
    """job/a/job/b/ for a job b in folder a."""
    return "".join("job/" + urllib.parse.quote(part, safe="") + "/" for part in name.split("/"))
'''


def jenkins_spec(config: JenkinsConnection, main: str, env: dict[str, str]) -> ScriptSpec:
    """A script that runs CLIENT and then `main` with python3, given the connection."""
    return ScriptSpec(
        script=f"python3 - <<'PY'\n{CLIENT}\n{main.strip()}\nPY\n",
        env={"JENKINS_URL": config.url, "JENKINS_USER": config.username, **env},
    )


def token_env(config: JenkinsConnection) -> list[SecretEnv]:
    secret_id: uuid.UUID = config.token_secret_id
    return [SecretEnv(name="JENKINS_TOKEN", secret_id=secret_id)]


def failure_detail(output: str, exit_code: int | None) -> str:
    """The script's own message for a failed probe."""
    lines = output.strip().splitlines()
    return lines[-1] if lines else f"The check exited with {exit_code}"
