"""The Pi-hole feature, run against a fake Pi-hole v6 API that answers like the real one."""

import json
import os
import subprocess
import threading
import uuid
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import ValidationError

from app.features import pihole
from app.features.base import ProbeResult
from app.models import StateTone
from app.schemas.actions import ScriptSpec

PASSWORD = "app-password-123"
SECRET_ID = uuid.uuid4()


class FakePihole:
    """Answers /api/auth, /api/dns/blocking, and /api/stats/summary as Pi-hole 6 does
    (bodies copied from a real one), and counts open sessions."""

    def __init__(self) -> None:
        self.blocking = "enabled"
        self.timer: float | None = None
        self.sessions: set[str] = set()
        self.requests: list[tuple[str, str, object]] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, status: int, body: object = None, headers: dict | None = None) -> None:
                payload = b"" if body is None else json.dumps(body).encode()
                self.send_response(status)
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _handle(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                fake.requests.append((self.command, self.path, body))
                unauthorized = {"error": {"key": "unauthorized", "message": "Unauthorized"}}
                if self.path.startswith("/moved/"):
                    return self._send(302, headers={"Location": "https://elsewhere.test/api/auth"})
                if self.path == "/api/auth" and self.command == "POST":
                    if not isinstance(body, dict) or body.get("password") != PASSWORD:
                        return self._send(401, unauthorized)
                    sid = uuid.uuid4().hex
                    fake.sessions.add(sid)
                    session = {"valid": True, "totp": False, "sid": sid, "validity": 1800}
                    return self._send(200, {"session": session, "took": 0.03})
                sid = self.headers.get("X-FTL-SID")
                if sid not in fake.sessions:
                    return self._send(401, unauthorized)
                if self.path == "/api/auth" and self.command == "DELETE":
                    fake.sessions.discard(sid)
                    return self._send(204)
                if self.path == "/api/dns/blocking" and self.command == "POST":
                    assert isinstance(body, dict)
                    fake.blocking = "enabled" if body["blocking"] else "disabled"
                    fake.timer = body.get("timer")
                if self.path == "/api/dns/blocking":
                    return self._send(200, {"blocking": fake.blocking, "timer": fake.timer})
                if self.path == "/api/stats/summary":
                    queries = {"total": 12345, "blocked": 2222, "percent_blocked": 18.0}
                    return self._send(200, {"queries": queries, "gravity": {}})
                return self._send(404, {"error": {"key": "not_found"}})

            do_GET = do_POST = do_DELETE = _handle

            def log_message(self, *args: object) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def __enter__(self) -> "FakePihole":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._server.shutdown()
        self._server.server_close()


@pytest.fixture
def fake() -> Iterator[FakePihole]:
    with FakePihole() as server:
        yield server


def _config(url: str, **extra: object) -> pihole.ConfigModel:
    return pihole.ConfigModel.model_validate(
        {"url": url, "password_secret_id": str(SECRET_ID), **extra}
    )


def _run(spec: object, password: str = PASSWORD) -> ProbeResult:
    """Run a Pi-hole script as the local executor would, with the password from secret_env."""
    assert isinstance(spec, ScriptSpec)
    result = subprocess.run(  # noqa: S603 - the feature's own fixed script
        ["/bin/sh", "-c", spec.script],
        env={**os.environ, **spec.env, "PIHOLE_PASSWORD": password},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return ProbeResult(result.returncode, result.stdout + result.stderr)


def test_build_keeps_the_password_out_of_the_config_and_script() -> None:
    config = _config("http://pi.hole", pause_minutes=10)
    built = pihole.build(config)
    assert [(a.key, a.name, a.confirm) for a in built.actions] == [
        ("pause", "Pause ad blocking 10 min", False),
        ("resume", "Resume ad blocking", False),
    ]
    for action in built.actions:
        assert [(s.name, s.secret_id) for s in action.secret_env] == [
            ("PIHOLE_PASSWORD", SECRET_ID)
        ]
        assert isinstance(action.spec, ScriptSpec)
        assert action.spec.env == {"PIHOLE_URL": "http://pi.hole", "PAUSE_SECONDS": "600"}
    assert [(t.state_key, t.label) for t in built.tiles] == [("blocking", "pi.hole")]
    assert pihole.probe(config).secret_env == built.actions[0].secret_env


@pytest.mark.parametrize(
    "field",
    [
        {"url": "pi.hole"},
        {"url": "http://pi.hole/ x"},
        {"pause_minutes": 0},
        {"pause_minutes": 2000},
    ],
)
def test_bad_config_is_refused(field: dict) -> None:
    with pytest.raises(ValidationError):
        _config(**{"url": "http://pi.hole", **field})


def test_pause_resume_and_status(fake: FakePihole) -> None:
    # The address of the web interface works too, as people copy it from the browser.
    config = _config(fake.url + "/admin/", pause_minutes=5)
    actions = {a.key: a for a in pihole.build(config).actions}

    def state() -> tuple[str, StateTone, str]:
        [value] = pihole.parse(config, _run(pihole.probe(config).spec))
        return value.value, value.tone, value.detail

    assert state() == ("blocking", StateTone.GOOD, "18.0% of 12,345 queries blocked (24 h)")
    paused = _run(actions["pause"].spec)
    assert (paused.exit_code, paused.output) == (0, "Ad blocking is paused for 5 min.\n")
    assert (fake.blocking, fake.timer) == ("disabled", 300)
    assert state() == ("paused", StateTone.WARN, "Back on in 5 min")
    resumed = _run(actions["resume"].spec)
    assert (resumed.exit_code, resumed.output) == (0, "Ad blocking is on again.\n")
    assert (fake.blocking, fake.timer) == ("enabled", None)
    # Every script logs out again: Pi-hole allows only a few sessions.
    assert fake.sessions == set()
    assert all(PASSWORD not in json.dumps(r[2]) for r in fake.requests if r[1] != "/api/auth")


def test_a_wrong_password_is_explained(fake: FakePihole) -> None:
    config = _config(fake.url)
    result = _run(pihole.probe(config).spec, password="nope")
    assert result.exit_code == 5
    [state] = pihole.parse(config, result)
    assert (state.value, state.tone, state.detail) == (
        "unknown",
        StateTone.UNKNOWN,
        "Pi-hole rejected the password",
    )


def test_redirects_are_not_followed(fake: FakePihole) -> None:
    # The password is sent only to the configured address, never on to where it points.
    config = _config(fake.url + "/moved")
    result = _run(pihole.probe(config).spec)
    assert result.exit_code == 6
    assert "redirected to https://elsewhere.test/api/auth" in result.output
    assert [path for _, path, _ in fake.requests] == ["/moved/api/auth"]


def test_an_unreachable_pihole_is_down() -> None:
    config = _config("http://127.0.0.1:9")
    result = _run(pihole.probe(config).spec)
    assert result.exit_code == 7
    [state] = pihole.parse(config, result)
    assert (state.value, state.tone) == ("down", StateTone.BAD)
    assert state.detail.startswith("Could not reach Pi-hole")


def test_parse() -> None:
    config = _config("http://pi.hole")

    def parsed(info: dict) -> tuple[str, StateTone, str]:
        [state] = pihole.parse(config, ProbeResult(0, "pihole " + json.dumps(info)))
        return state.value, state.tone, state.detail

    stats = {"total": 0, "percent_blocked": 0}
    assert parsed({"blocking": "enabled", "timer": None, **stats}) == (
        "blocking",
        StateTone.GOOD,
        "0.0% of 0 queries blocked (24 h)",
    )
    assert parsed({"blocking": "disabled", "timer": 299.7, **stats})[2] == "Back on in 5 min"
    assert parsed({"blocking": "disabled", "timer": 42, **stats})[2] == "Back on in 42 s"
    assert parsed({"blocking": "disabled", "timer": None, **stats})[2] == "Off until turned on"
    assert parsed({"blocking": "failed", "timer": None, **stats})[:2] == ("failed", StateTone.BAD)
    [lost] = pihole.parse(config, ProbeResult(None, "", error="timed out"))
    assert (lost.value, lost.detail) == ("unknown", "timed out")
    [odd] = pihole.parse(config, ProbeResult(0, "something else"))
    assert odd.value == "unknown"
