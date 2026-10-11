"""Live SSE streaming against a real server (TestClient buffers streaming responses)."""

import json
import socket
import threading
import time
from collections.abc import Iterator

import httpx2 as httpx
import pytest
import uvicorn

from app.config import Settings
from app.main import create_app
from app.security import CSRF_HEADER, CSRF_HEADER_VALUE
from tests.conftest import ADMIN


@pytest.fixture
def live_url(settings: Settings) -> Iterator[str]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)


def test_output_streams_before_the_run_finishes(live_url: str) -> None:
    with httpx.Client(base_url=live_url, headers={CSRF_HEADER: CSRF_HEADER_VALUE}) as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        action = client.post(
            "/api/v1/actions",
            json={
                "name": "slow",
                "executor": "local",
                "spec": {"script": "echo first; sleep 2; echo second"},
            },
        ).json()
        started = time.monotonic()
        run = client.post(f"/api/v1/actions/{action['id']}/run", json={"args": {}}).json()

        arrivals: list[tuple[float, str, object]] = []
        event = None
        with client.stream("GET", f"/api/v1/runs/{run['id']}/stream", timeout=10) as stream:
            for line in stream.iter_lines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    data = json.loads(line.removeprefix("data: "))
                    arrivals.append((time.monotonic() - started, event or "", data))

    first_at = next(t for t, name, data in arrivals if name == "output" and "first" in str(data))
    end_at, end_name, end = arrivals[-1]
    assert first_at < 1.5, "first line should arrive while the run is still sleeping"
    assert end_name == "end"
    assert end_at >= 2
    assert end["status"] == "succeeded"  # type: ignore[index]
