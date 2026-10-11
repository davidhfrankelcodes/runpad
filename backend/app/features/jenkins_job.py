"""Build a Jenkins job and watch it: its console output streams into the Run, which ends with
the build's result. Also stop the running build, show the last build's log, and a tile with
the last build's result."""

import json
import re

from pydantic import Field, field_validator

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

# Jenkins runs builds for as long as they take; a Run watches for at most this long.
WATCH_SECONDS = 3600
LOG_LINES = 500
_PARAMETER = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*=[^\n]*$")


class ConfigModel(JenkinsConnection):
    job: str = Field(
        title="Job",
        description="The job's name; for a job in a folder, folder/job.",
        pattern=r"^[^/\x00-\x1f]+(/[^/\x00-\x1f]+)*$",
        max_length=255,
    )
    parameters: str = Field(
        default="",
        title="Build parameters",
        description="Optional, one NAME=value per line. Each build gets these values.",
        max_length=5000,
        json_schema_extra={"x-multiline": True},
    )

    @field_validator("parameters")
    @classmethod
    def _parameter_lines(cls, value: str) -> str:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        for line in lines:
            if not _PARAMETER.match(line):
                raise ValueError(f"Not NAME=value: {line[:40]}")
        return "\n".join(lines)

    def short_name(self) -> str:
        return self.job.rsplit("/", 1)[-1]


# Queue the build, wait for it to start, stream its console, and exit with its result.
BUILD = r"""
job = job_path(os.environ["JOB"])
params = [tuple(line.split("=", 1)) for line in os.environ.get("PARAMS", "").splitlines() if line]
# A job that takes parameters must be built with buildWithParameters (Jenkins answers 400 to
# build); parameters left out get the job's defaults.
definitions = get_json(job, "property[parameterDefinitions[name]]").get("property") or []
takes_parameters = any(p.get("parameterDefinitions") for p in definitions)
if params and not takes_parameters:
    fail(os.environ["JOB"] + " takes no parameters; remove the build parameters in runpad.", 9)
if takes_parameters:
    queued = call(job + "buildWithParameters", "POST", urllib.parse.urlencode(params).encode())
else:
    queued = call(job + "build", "POST", b"")
location = queued.headers.get("Location") or ""
item = location.rstrip("/").rsplit("/", 1)[-1]
if "/queue/item/" not in location or not item.isdigit():
    fail("Jenkins accepted the build but did not say where it was queued", 6)
print("Queued " + os.environ["JOB"], flush=True)

reason = None
while True:
    queue = get_json("queue/item/" + item + "/")
    if queue.get("cancelled"):
        fail("The build was cancelled while it waited in the queue", 8)
    if queue.get("executable"):
        number = queue["executable"]["number"]
        break
    if queue.get("why") and queue["why"] != reason:
        reason = queue["why"]
        print("Waiting: " + reason, flush=True)
    time.sleep(2)

build = job + str(number) + "/"
print("Build #%d started" % number, flush=True)
start, log = 0, LogText()
while True:
    response = call(build + "logText/progressiveText?start=%d" % start)
    sys.stdout.write(log.feed(response.read().decode("utf-8", "replace")))
    sys.stdout.flush()
    start = int(response.headers.get("X-Text-Size") or start)
    if response.headers.get("X-More-Data") != "true":
        break
    time.sleep(2)
sys.stdout.write(log.flush())

while True:
    result = get_json(build, "building,result")
    if not result.get("building") and result.get("result"):
        break
    time.sleep(2)
print("Build #%d: %s" % (number, result["result"]), flush=True)
sys.exit(0 if result["result"] == "SUCCESS" else 1)
"""

STOP = r"""
job = job_path(os.environ["JOB"])
last = get_json(job, "lastBuild[number,building]").get("lastBuild")
if not last or not last.get("building"):
    print("No build of " + os.environ["JOB"] + " is running.")
    sys.exit(0)
call(job + "%d/stop" % last["number"], "POST", b"")
print("Asked Jenkins to stop build #%d" % last["number"])
"""

LOG = r"""
job = job_path(os.environ["JOB"])
last = get_json(job, "lastBuild[number,building,result]").get("lastBuild")
if not last:
    print(os.environ["JOB"] + " has not been built yet.")
    sys.exit(0)
text = call(job + "%d/consoleText" % last["number"]).read().decode("utf-8", "replace")
lines = NOTES.sub("", text).splitlines()
state = "still running" if last.get("building") else last.get("result")
print("Build #%d (%s), last %d lines:" % (last["number"], state, LOG_LINES))
print("\n".join(lines[-LOG_LINES:]))
""".replace("LOG_LINES", str(LOG_LINES))

# Prints one line: "job <JSON>" with the last build, whether one is queued, and the time.
STATUS = r"""
job = job_path(os.environ["JOB"])
info = get_json(job, "inQueue,lastBuild[number,building,result,timestamp,duration]")
info["now"] = int(time.time() * 1000)
print("job " + json.dumps(info))
"""


def _env(config: ConfigModel) -> dict[str, str]:
    return {"JOB": config.job, "PARAMS": config.parameters}


def _spec(config: ConfigModel, main: str) -> ScriptSpec:
    return jenkins_spec(config, main, _env(config))


def build(config: ConfigModel) -> Build:
    name = config.short_name()
    secrets = token_env(config)

    def action(
        key: str,
        verb: str,
        main: str,
        description: str,
        color: ButtonColor,
        *,
        timeout: int = 60,
        confirm: bool = False,
    ) -> ActionTemplate:
        return ActionTemplate(
            key=key,
            name=f"{verb} {name}",
            description=description,
            executor=Executor.LOCAL,
            spec=_spec(config, main),
            secret_env=secrets,
            timeout_seconds=timeout,
            confirm=confirm,
            button=ButtonTemplate(label=f"{verb} {name}", color=color),
        )

    return Build(
        actions=[
            action(
                "build",
                "Build",
                BUILD,
                f"Starts the {name} job in Jenkins and shows its output until it finishes. "
                "Closing the output does not stop the build.",
                ButtonColor.EMERALD,
                timeout=WATCH_SECONDS,
            ),
            action(
                "stop",
                "Stop",
                STOP,
                f"Stops the running build of {name} in Jenkins.",
                ButtonColor.RED,
                confirm=True,
            ),
            action(
                "log",
                "Log of",
                LOG,
                f"Shows the end of the last {name} build's output.",
                ButtonColor.SLATE,
            ),
        ],
        tiles=[TileTemplate(state_key="last_build", label=name)],
    )


def probe(config: ConfigModel) -> Probe:
    return Probe(
        executor=Executor.LOCAL,
        spec=_spec(config, STATUS),
        secret_env=token_env(config),
        timeout_seconds=40,
    )


_RESULTS = {
    "SUCCESS": ("succeeded", StateTone.GOOD),
    "UNSTABLE": ("unstable", StateTone.WARN),
    "FAILURE": ("failed", StateTone.BAD),
    "ABORTED": ("aborted", StateTone.NEUTRAL),
    "NOT_BUILT": ("not built", StateTone.NEUTRAL),
}


def _took(ms: int) -> str:
    seconds = round(ms / 1000)
    if seconds < 60:
        return f"{seconds} s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {seconds} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def parse(config: ConfigModel, result: ProbeResult) -> list[StateValue]:
    lines = result.output.strip().splitlines()
    last = lines[-1] if lines else ""
    if result.error is not None:
        return [StateValue("last_build", "unknown", StateTone.UNKNOWN, result.error)]
    if result.exit_code == 4:
        detail = f"No job {config.job} on this Jenkins"
        return [StateValue("last_build", "not found", StateTone.BAD, detail)]
    if result.exit_code != 0 or not last.startswith("job "):
        detail = failure_detail(result.output, result.exit_code)
        return [StateValue("last_build", "unknown", StateTone.UNKNOWN, detail)]
    try:
        info = json.loads(last.removeprefix("job "))
    except ValueError:
        return [StateValue("last_build", "unknown", StateTone.UNKNOWN, "Unexpected answer")]
    queued = " · another build queued" if info.get("inQueue") else ""
    build = info.get("lastBuild")
    if not build:
        value = "queued" if info.get("inQueue") else "never built"
        return [StateValue("last_build", value, StateTone.NEUTRAL, "")]
    number = build.get("number")
    if build.get("building"):
        running = _took(max(0, info.get("now", 0) - build.get("timestamp", 0)))
        detail = f"#{number} · running for {running}{queued}"
        return [StateValue("last_build", "running", StateTone.NEUTRAL, detail)]
    value, tone = _RESULTS.get(
        str(build.get("result")), (str(build.get("result")).lower(), StateTone.NEUTRAL)
    )
    detail = f"#{number} · took {_took(build.get('duration') or 0)}{queued}"
    return [StateValue("last_build", value, tone, detail)]


FEATURE = Feature(
    id="jenkins_job",
    name="Jenkins job",
    description="Build a Jenkins job and watch its output live, stop it, see its last log, "
    "and see how the last build went.",
    icon="jenkins",
    category="CI/CD",
    ConfigModel=ConfigModel,
    build=build,
    poll=Poll(probe=probe, parse=parse),
)
