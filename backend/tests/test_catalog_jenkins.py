"""The Jenkins features, against a fake Jenkins that checks credentials and serves the
endpoints the scripts use: queueing, the progressive console log, results, and agents."""

import base64
import json
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.executors import local
from app.features import jenkins_agent, jenkins_job
from app.features.base import ProbeResult
from app.models import Executor, StateTone
from app.schemas.actions import ScriptSpec
from tests.helpers import enable_feature, managed_actions, run_and_wait

USER, TOKEN = "ci", "11aa22bb33cc44dd55ee66ff77"
SECRET_ID = uuid.uuid4()


class FakeJenkins:
    """One job, "team/deploy", and one agent, "builder 1"."""

    def __init__(self, result: str = "SUCCESS", parameterized: bool = False) -> None:
        self.result = result
        self.parameterized = parameterized
        self.requests: list[tuple[str, str, dict[str, list[str]]]] = []
        self.building = False
        self.agent = {"offline": False, "temporarilyOffline": False, "idle": True}
        # Like real Jenkins, the log hides console notes in escape sequences.
        note = "\x1b[8mha:////4PazcDkW5dQ0nFXnLyGx1ibC+wfVc8P==\x1b[0m"
        self.log = [f"Started by user {note}ci", "Deploying...", f"Finished: {result}"]
        self.chunks = 2  # The progressive log arrives in this many requests.
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, body: object = b"", headers: dict | None = None) -> None:
                payload = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _handle(self) -> None:
                expected = "Basic " + base64.b64encode(f"{USER}:{TOKEN}".encode()).decode()
                if self.headers.get("Authorization") != expected:
                    return self._send(401, {"error": "unauthorized"})
                length = int(self.headers.get("Content-Length") or 0)
                form = parse_qs(self.rfile.read(length).decode()) if length else {}
                path = urlsplit(self.path).path
                fake.requests.append((self.command, path, form))
                job = "/job/team/job/deploy/"
                node = "/computer/builder%201/"
                if self.command == "POST" and path == job + "build" and fake.parameterized:
                    return self._send(400, b"Nothing is submitted")  # As real Jenkins does.
                if self.command == "POST" and path == job + "buildWithParameters":
                    if not fake.parameterized:
                        return self._send(400, b"deploy is not parameterized")
                    return self._send(201, headers={"Location": "http://ci.internal/queue/item/7/"})
                if self.command == "POST" and path == job + "build":
                    # Jenkins builds the Location from its own root URL, which may differ.
                    return self._send(201, headers={"Location": "http://ci.internal/queue/item/7/"})
                if path == "/queue/item/7/api/json":
                    return self._send(200, {"executable": {"number": 3, "url": "http://x/"}})
                if path == job + "3/logText/progressiveText":
                    # Split in the middle of the console note, as chunks can be.
                    text = "\n".join(fake.log) + "\n"
                    start = int(parse_qs(urlsplit(self.path).query)["start"][0])
                    end = len(text) if fake.chunks == 1 or start else 30
                    headers = {"X-Text-Size": str(end)}
                    if end < len(text):
                        headers["X-More-Data"] = "true"
                    return self._send(200, text[start:end].encode(), headers)
                if path == job + "3/api/json":
                    return self._send(200, {"building": False, "result": fake.result})
                if path == job + "api/json":
                    last = {
                        "number": 3,
                        "building": fake.building,
                        "result": None if fake.building else fake.result,
                        "timestamp": 1_000_000,
                        "duration": 0 if fake.building else 125_000,
                    }
                    definitions = [{"name": "BRANCH"}] if fake.parameterized else []
                    prop = [{"parameterDefinitions": definitions}] if definitions else [{}]
                    return self._send(200, {"inQueue": False, "lastBuild": last, "property": prop})
                if self.command == "POST" and path == job + "3/stop":
                    return self._send(302, headers={"Location": "http://ci.internal/job/x/"})
                if path == job + "3/consoleText":
                    return self._send(200, ("\n".join(fake.log) + "\n").encode())
                if path == node + "api/json":
                    return self._send(200, {**fake.agent, "numExecutors": 2})
                if self.command == "POST" and path == node + "toggleOffline":
                    fake.agent["offline"] = fake.agent["temporarilyOffline"] = not fake.agent[
                        "offline"
                    ]
                    return self._send(302, headers={"Location": "/computer/"})
                return self._send(404, {"error": "not found"})

            do_GET = do_POST = _handle

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeJenkins":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()

    def paths(self, method: str) -> list[str]:
        return [path for m, path, _ in self.requests if m == method]


@pytest.fixture
def jenkins() -> Iterator[FakeJenkins]:
    with FakeJenkins() as fake:
        yield fake


def _job(url: str, **extra: str) -> jenkins_job.ConfigModel:
    return jenkins_job.ConfigModel(
        url=url, username=USER, token_secret_id=SECRET_ID, job="team/deploy", **extra
    )


def _agent(url: str) -> jenkins_agent.ConfigModel:
    return jenkins_agent.ConfigModel(
        url=url, username=USER, token_secret_id=SECRET_ID, node="builder 1"
    )


def _run(spec: object, token: str = TOKEN) -> ProbeResult:
    """Run a Jenkins script as the local executor would, with the token from secret_env."""
    assert isinstance(spec, ScriptSpec)
    result = subprocess.run(  # noqa: S603 - the feature's own fixed script
        ["/bin/sh", "-c", spec.script],
        env={**os.environ, **spec.env, "JENKINS_TOKEN": token},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return ProbeResult(result.returncode, result.stdout + result.stderr)


def _actions(config: jenkins_job.ConfigModel | jenkins_agent.ConfigModel) -> dict:
    module = jenkins_job if isinstance(config, jenkins_job.ConfigModel) else jenkins_agent
    return {a.key: a for a in module.build(config).actions}


# --- Jenkins job: build() --------------------------------------------------


def test_job_build_keeps_the_token_out_of_the_config_and_script() -> None:
    config = _job("http://jenkins.lan:8080")
    built = jenkins_job.build(config)
    assert [(a.key, a.name, a.confirm) for a in built.actions] == [
        ("build", "Build deploy", False),
        ("stop", "Stop deploy", True),
        ("log", "Log of deploy", False),
    ]
    for action in built.actions:
        assert action.executor == Executor.LOCAL
        assert [(s.name, s.secret_id) for s in action.secret_env] == [("JENKINS_TOKEN", SECRET_ID)]
        assert isinstance(action.spec, ScriptSpec)
        assert action.spec.env == {
            "JENKINS_URL": "http://jenkins.lan:8080",
            "JENKINS_USER": USER,
            "JOB": "team/deploy",
            "PARAMS": "",
        }
        assert "team/deploy" not in action.spec.script
    assert built.actions[0].timeout_seconds == 3600
    assert [(t.state_key, t.label) for t in built.tiles] == [("last_build", "deploy")]
    probe = jenkins_job.probe(config)
    assert [s.name for s in probe.secret_env] == ["JENKINS_TOKEN"]


@pytest.mark.parametrize(
    "field",
    [
        {"url": "jenkins.lan"},
        {"username": "a b"},
        {"job": "/deploy"},
        {"job": "a//b"},
        {"parameters": "no equals sign"},
        {"parameters": "1BAD=x"},
    ],
)
def test_job_rejects_bad_config(field: dict) -> None:
    body = {
        "url": "http://j",
        "username": USER,
        "token_secret_id": str(SECRET_ID),
        "job": "deploy",
        **field,
    }
    with pytest.raises(ValidationError):
        jenkins_job.ConfigModel(**body)


def test_job_parameters_are_normalized() -> None:
    config = _job("http://j", parameters="  BRANCH=main\n\nDRY_RUN=true  \n")
    assert config.parameters == "BRANCH=main\nDRY_RUN=true"


# --- Jenkins job: scripts against the fake ---------------------------------


def test_build_streams_the_console_and_succeeds(jenkins: FakeJenkins) -> None:
    result = _run(_actions(_job(jenkins.url))["build"].spec)
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == [
        "Queued team/deploy",
        "Build #3 started",
        "Started by user ci",
        "Deploying...",
        "Finished: SUCCESS",
        "Build #3: SUCCESS",
    ]
    assert jenkins.paths("POST") == ["/job/team/job/deploy/build"]
    assert "\x1b" not in result.output  # The console note was removed, though split.


def test_a_failed_build_fails_the_run() -> None:
    with FakeJenkins(result="FAILURE") as jenkins:
        result = _run(_actions(_job(jenkins.url))["build"].spec)
    assert result.exit_code == 1
    assert result.output.strip().endswith("Build #3: FAILURE")


def test_build_sends_parameters() -> None:
    with FakeJenkins(parameterized=True) as jenkins:
        config = _job(jenkins.url, parameters="BRANCH=release/2.0\nDRY_RUN=true")
        assert _run(_actions(config)["build"].spec).exit_code == 0
    [(_, path, form)] = [r for r in jenkins.requests if r[0] == "POST"]
    assert path == "/job/team/job/deploy/buildWithParameters"
    assert form == {"BRANCH": ["release/2.0"], "DRY_RUN": ["true"]}


def test_a_job_with_parameters_builds_with_its_defaults() -> None:
    with FakeJenkins(parameterized=True) as jenkins:
        result = _run(_actions(_job(jenkins.url))["build"].spec)
    assert result.exit_code == 0, result.output
    [(_, path, form)] = [r for r in jenkins.requests if r[0] == "POST"]
    assert (path, form) == ("/job/team/job/deploy/buildWithParameters", {})


def test_parameters_for_a_job_without_any_are_refused(jenkins: FakeJenkins) -> None:
    result = _run(_actions(_job(jenkins.url, parameters="BRANCH=main"))["build"].spec)
    assert result.exit_code == 9
    assert "takes no parameters" in result.output
    assert jenkins.paths("POST") == []


def test_wrong_credentials_and_missing_jobs_are_explained(jenkins: FakeJenkins) -> None:
    result = _run(_actions(_job(jenkins.url))["build"].spec, token="wrong")
    assert result.exit_code == 5
    assert "rejected the user name or API token" in result.output
    missing = jenkins_job.ConfigModel(
        url=jenkins.url, username=USER, token_secret_id=SECRET_ID, job="nope"
    )
    result = _run(_actions(missing)["build"].spec)
    assert result.exit_code == 4
    assert result.output.strip() == f"Jenkins has nothing at {jenkins.url}/job/nope/"


def test_unreachable_jenkins_is_explained() -> None:
    result = _run(_actions(_job("http://127.0.0.1:9"))["build"].spec)
    assert result.exit_code == 7
    assert result.output.startswith("Could not reach Jenkins")


def test_stop_only_stops_a_running_build(jenkins: FakeJenkins) -> None:
    stop = _actions(_job(jenkins.url))["stop"].spec
    assert _run(stop).output.strip() == "No build of team/deploy is running."
    jenkins.building = True
    result = _run(stop)
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "Asked Jenkins to stop build #3"
    assert jenkins.paths("POST") == ["/job/team/job/deploy/3/stop"]


def test_log_shows_the_last_build(jenkins: FakeJenkins) -> None:
    result = _run(_actions(_job(jenkins.url))["log"].spec)
    assert result.exit_code == 0
    assert result.output.splitlines()[0] == "Build #3 (SUCCESS), last 500 lines:"
    assert "Deploying..." in result.output


def test_job_probe_reports_the_last_build(jenkins: FakeJenkins) -> None:
    config = _job(jenkins.url)
    result = _run(jenkins_job.probe(config).spec)
    [state] = jenkins_job.parse(config, result)
    assert (state.value, state.tone, state.detail) == (
        "succeeded",
        StateTone.GOOD,
        "#3 · took 2 min 5 s",
    )


# --- Jenkins job: parse() --------------------------------------------------

JOB = _job("http://j")


def _job_state(info: dict, exit_code: int = 0) -> tuple[str, StateTone, str]:
    [state] = jenkins_job.parse(JOB, ProbeResult(exit_code, "job " + json.dumps(info)))
    return state.value, state.tone, state.detail


@pytest.mark.parametrize(
    ("build", "expected"),
    [
        (
            {"number": 9, "result": "UNSTABLE", "duration": 4000},
            ("unstable", StateTone.WARN, "#9 · took 4 s"),
        ),
        (
            {"number": 9, "result": "FAILURE", "duration": 4000},
            ("failed", StateTone.BAD, "#9 · took 4 s"),
        ),
        (
            {"number": 9, "result": "ABORTED", "duration": 0},
            ("aborted", StateTone.NEUTRAL, "#9 · took 0 s"),
        ),
        (
            {"number": 9, "building": True, "timestamp": 1000},
            ("running", StateTone.NEUTRAL, "#9 · running for 1 h 1 min"),
        ),
    ],
)
def test_job_parse(build: dict, expected: tuple) -> None:
    assert _job_state({"inQueue": False, "lastBuild": build, "now": 1000 + 3_660_000}) == expected


def test_job_parse_edge_cases() -> None:
    assert _job_state({"inQueue": False, "lastBuild": None}) == (
        "never built",
        StateTone.NEUTRAL,
        "",
    )
    assert _job_state({"inQueue": True, "lastBuild": None})[0] == "queued"
    queued_again = _job_state(
        {"inQueue": True, "lastBuild": {"number": 2, "result": "SUCCESS", "duration": 1000}}
    )
    assert queued_again[2] == "#2 · took 1 s · another build queued"
    [missing] = jenkins_job.parse(JOB, ProbeResult(4, "Jenkins has nothing at http://j/job/x/"))
    assert (missing.value, missing.tone) == ("not found", StateTone.BAD)
    [denied] = jenkins_job.parse(
        JOB, ProbeResult(5, "Jenkins rejected the user name or API token (HTTP 401)\n")
    )
    assert (denied.value, denied.detail) == (
        "unknown",
        "Jenkins rejected the user name or API token (HTTP 401)",
    )


# --- Jenkins agent ---------------------------------------------------------


def test_agent_build() -> None:
    built = jenkins_agent.build(_agent("http://j"))
    assert [(a.key, a.name, a.confirm) for a in built.actions] == [
        ("offline", "Take builder 1 offline", True),
        ("online", "Bring builder 1 online", False),
    ]
    assert all(a.secret_env[0].name == "JENKINS_TOKEN" for a in built.actions)
    assert [(t.state_key, t.label) for t in built.tiles] == [("agent", "builder 1")]


def test_agent_offline_and_online(jenkins: FakeJenkins) -> None:
    config = _agent(jenkins.url)
    actions = _actions(config)

    def state() -> tuple[str, StateTone, str]:
        [value] = jenkins_agent.parse(config, _run(jenkins_agent.probe(config).spec))
        return value.value, value.tone, value.detail

    assert state() == ("idle", StateTone.GOOD, "2 executors")
    result = _run(actions["offline"].spec)
    assert result.exit_code == 0, result.output
    assert jenkins.agent["temporarilyOffline"] is True
    assert state()[:2] == ("paused", StateTone.WARN)
    assert "already offline" in _run(actions["offline"].spec).output
    assert "back online" in _run(actions["online"].spec).output
    assert state()[0] == "idle"
    toggles = [r for r in jenkins.requests if r[1].endswith("toggleOffline")]
    assert toggles[0][2] == {"offlineMessage": ["Taken offline from runpad"]}
    assert len(toggles) == 2


def test_agent_parse() -> None:
    config = _agent("http://j")

    def parsed(info: dict) -> tuple[str, StateTone, str]:
        [state] = jenkins_agent.parse(config, ProbeResult(0, "node " + json.dumps(info)))
        return state.value, state.tone, state.detail

    assert parsed({"offline": False, "idle": False, "numExecutors": 1}) == (
        "busy",
        StateTone.GOOD,
        "1 executor",
    )
    assert parsed({"offline": True, "temporarilyOffline": False, "offlineCauseReason": ""}) == (
        "offline",
        StateTone.BAD,
        "Disconnected",
    )
    [missing] = jenkins_agent.parse(config, ProbeResult(4, "Jenkins has nothing at x"))
    assert missing.value == "not found"


# --- Through the API: secrets ----------------------------------------------


def test_enabling_checks_the_secret_and_runs_with_it(
    admin_client: TestClient, jenkins: FakeJenkins, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The local executor's minimal PATH has no python3 in the test container; add this one.
    monkeypatch.setitem(local.BASE_ENV, "PATH", f"{Path(sys.executable).parent}:/usr/bin:/bin")
    secret = admin_client.post(
        "/api/v1/secrets", json={"name": "jenkins", "kind": "text", "value": TOKEN}
    ).json()
    key = admin_client.post("/api/v1/secrets/generate-ssh-key", json={"name": "k"}).json()
    config = {
        "url": jenkins.url,
        "username": USER,
        "job": "team/deploy",
    }
    for wrong, message in [(key["id"], "needs a text secret"), (str(uuid.uuid4()), "not found")]:
        response = admin_client.post(
            "/api/v1/feature-instances",
            json={
                "feature_id": "jenkins_job",
                "item": "build",
                "config": {**config, "token_secret_id": wrong},
            },
        )
        assert response.status_code == 400
        assert message in response.json()["detail"]

    instance = enable_feature(
        admin_client, "jenkins_job", {**config, "token_secret_id": secret["id"]}, item="build"
    )
    actions = managed_actions(admin_client, instance)
    build = actions["Build deploy"]
    assert build["secret_env"] == [{"name": "JENKINS_TOKEN", "secret_id": secret["id"]}]
    run = run_and_wait(admin_client, build)
    assert run["status"] == "succeeded", run
    assert "Build #3: SUCCESS" in run["output"]
    assert TOKEN not in run["output"]

    # The secret cannot be deleted while the feature's actions use it.
    response = admin_client.delete(f"/api/v1/secrets/{secret['id']}")
    assert response.status_code == 409
    assert "Build deploy" in response.json()["detail"]
