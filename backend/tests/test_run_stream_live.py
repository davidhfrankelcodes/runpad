"""Live SSE streaming against a real server (TestClient buffers streaming responses)."""

import json
import time

import httpx2 as httpx

from app.security import CSRF_HEADER, CSRF_HEADER_VALUE
from tests.conftest import ADMIN


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
