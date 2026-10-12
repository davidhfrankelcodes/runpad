import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import plain_url

FINISHED = {"succeeded", "failed", "timed_out", "cancelled", "interrupted"}


def _action(client: TestClient, script: str, **extra: object) -> dict:
    body = {"name": "test", "executor": "local", "spec": {"script": script}, **extra}
    response = client.post("/api/v1/actions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _start(client: TestClient, action: dict, args: dict | None = None) -> dict:
    response = client.post(f"/api/v1/actions/{action['id']}/run", json={"args": args or {}})
    assert response.status_code == 202, response.text
    return response.json()


def _wait(client: TestClient, run: dict, timeout: float = 10) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = client.get(f"/api/v1/runs/{run['id']}").json()
        if current["status"] in FINISHED:
            return current
        time.sleep(0.05)
    raise AssertionError(f"run did not finish: {current}")


def _wait_for_file(path: Path, timeout: float = 10) -> None:
    """Wait for a marker file a script creates once it is running.

    (TestClient buffers streaming responses, so the SSE stream cannot be used for this.)
    """
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError(f"{path} was not created")
        time.sleep(0.02)


def test_run_succeeds_and_records_output(admin_client: TestClient) -> None:
    run = _start(admin_client, _action(admin_client, "echo hello"))
    assert run["status"] == "running"
    assert run["triggered_by"] == "admin"
    done = _wait(admin_client, run)
    assert done["status"] == "succeeded"
    assert done["exit_code"] == 0
    assert done["output"] == "hello\n"
    assert done["finished_at"] is not None


def test_nonzero_exit_is_failed(admin_client: TestClient) -> None:
    done = _wait(admin_client, _start(admin_client, _action(admin_client, "echo bad; exit 4")))
    assert (done["status"], done["exit_code"], done["output"]) == ("failed", 4, "bad\n")


def test_timeout_kills_the_run(admin_client: TestClient) -> None:
    action = _action(admin_client, "echo start; sleep 30", timeout_seconds=1)
    done = _wait(admin_client, _start(admin_client, action))
    assert done["status"] == "timed_out"
    assert done["output"] == "start\n"
    assert done["error"] == "Timed out after 1 seconds"


def test_typed_args_reach_the_script(admin_client: TestClient) -> None:
    action = _action(
        admin_client,
        'echo "$ARG_NAME x$1 $ARG_TIMES"',
        args=[
            {"name": "name", "type": "string", "pattern": ".+"},
            {"name": "times", "type": "integer", "min": 1, "max": 3, "default": 2},
        ],
    )
    hostile = "$(echo pwned); echo pwned"
    done = _wait(admin_client, _start(admin_client, action, {"name": hostile}))
    assert done["output"] == f"{hostile} x{hostile} 2\n"
    assert done["args"] == {"name": hostile, "times": 2}


def test_invalid_args_are_rejected_before_running(admin_client: TestClient) -> None:
    action = _action(
        admin_client, "true", args=[{"name": "n", "type": "integer", "min": 1, "max": 3}]
    )
    response = admin_client.post(f"/api/v1/actions/{action['id']}/run", json={"args": {"n": 9}})
    assert response.status_code == 400
    assert admin_client.get("/api/v1/runs").json()["runs"] == []


def test_concurrent_run_is_rejected_by_default(admin_client: TestClient, tmp_path: Path) -> None:
    marker = tmp_path / "started"
    action = _action(admin_client, f"touch {marker}; sleep 30")
    first = _start(admin_client, action)
    _wait_for_file(marker)
    second = admin_client.post(f"/api/v1/actions/{action['id']}/run", json={"args": {}})
    assert second.status_code == 409
    assert "already running" in second.json()["detail"]
    admin_client.post(f"/api/v1/runs/{first['id']}/cancel")


def test_concurrency_allow_permits_overlap(admin_client: TestClient) -> None:
    action = _action(admin_client, "echo up; sleep 30", concurrency="allow")
    first, second = _start(admin_client, action), _start(admin_client, action)
    for run in (first, second):
        assert admin_client.post(f"/api/v1/runs/{run['id']}/cancel").status_code == 204


def test_cancel_stops_the_run(admin_client: TestClient, tmp_path: Path) -> None:
    marker = tmp_path / "started"
    run = _start(admin_client, _action(admin_client, f"echo started; touch {marker}; sleep 30"))
    _wait_for_file(marker)
    assert admin_client.post(f"/api/v1/runs/{run['id']}/cancel").status_code == 204
    done = _wait(admin_client, run)
    assert done["status"] == "cancelled"
    assert done["output"] == "started\n"
    assert admin_client.post(f"/api/v1/runs/{run['id']}/cancel").status_code == 409


def test_stream_sends_output_then_end(admin_client: TestClient) -> None:
    run = _start(admin_client, _action(admin_client, "echo one; sleep 0.2; echo two"))
    events: list[tuple[str, object]] = []
    with admin_client.stream("GET", f"/api/v1/runs/{run['id']}/stream") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        name = None
        for line in stream.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, json.loads(line.removeprefix("data: "))))
    output = "".join(data for name, data in events if name == "output")  # type: ignore[misc]
    assert output == "one\ntwo\n"
    end_name, end = events[-1]
    assert end_name == "end"
    assert end["status"] == "succeeded"  # type: ignore[index]


def test_stream_of_finished_run_replays_output(admin_client: TestClient) -> None:
    done = _wait(admin_client, _start(admin_client, _action(admin_client, "echo replay")))
    with admin_client.stream("GET", f"/api/v1/runs/{done['id']}/stream") as stream:
        body = "".join(stream.iter_text())
    assert 'event: output\ndata: "replay\\n"' in body
    assert "event: end" in body


def test_secret_env_is_available_and_redacted(admin_client: TestClient, database_url: str) -> None:
    secret = admin_client.post(
        "/api/v1/secrets", json={"name": "tok", "kind": "text", "value": "s3cr3t-value"}
    ).json()
    action = _action(
        admin_client,
        'echo "token=$API_TOKEN"; printf "%s" "$API_TOKEN" | wc -c',
        secret_env=[{"name": "API_TOKEN", "secret_id": secret["id"]}],
    )
    done = _wait(admin_client, _start(admin_client, action))
    assert done["output"] == "token=[redacted]\n12\n"
    with psycopg.connect(plain_url(database_url)) as conn:
        [(stored,)] = conn.execute("SELECT output FROM runs").fetchall()
    assert "s3cr3t-value" not in stored
    # The secret cannot be deleted while the action uses it.
    response = admin_client.delete(f"/api/v1/secrets/{secret['id']}")
    assert response.status_code == 409
    assert "actions" in response.json()["detail"]


def test_secret_env_rejects_reserved_names(admin_client: TestClient) -> None:
    secret = admin_client.post(
        "/api/v1/secrets", json={"name": "tok", "kind": "text", "value": "x"}
    ).json()
    for name in ("PATH", "ARG_X", "lower"):
        response = admin_client.post(
            "/api/v1/actions",
            json={
                "name": "t",
                "executor": "local",
                "spec": {"script": "true"},
                "secret_env": [{"name": name, "secret_id": secret["id"]}],
            },
        )
        assert response.status_code == 422, name


def test_output_is_capped(admin_client: TestClient) -> None:
    script = "head -c 700000 /dev/zero | tr '\\0' 'x'"
    done = _wait(admin_client, _start(admin_client, _action(admin_client, script)))
    assert done["status"] == "succeeded"
    assert done["output_truncated"] is True
    assert len(done["output"]) == 512 * 1024


def test_deleting_action_keeps_run_history(admin_client: TestClient) -> None:
    action = _action(admin_client, "echo kept")
    done = _wait(admin_client, _start(admin_client, action))
    assert admin_client.delete(f"/api/v1/actions/{action['id']}").status_code == 204
    run = admin_client.get(f"/api/v1/runs/{done['id']}").json()
    assert (run["action_id"], run["action_name"], run["output"]) == (None, "test", "kept\n")


def test_members_cannot_run_or_see_others_runs(
    admin_client: TestClient, make_client: Callable
) -> None:
    done = _wait(admin_client, _start(admin_client, _action(admin_client, "echo hi")))
    member = {"username": "member", "password": "member password 1"}
    admin_client.post("/api/v1/users", json=member)
    browser: TestClient = make_client()
    browser.post("/api/v1/auth/login", json=member)
    assert browser.post(f"/api/v1/actions/{done['action_id']}/run", json={}).status_code == 403
    assert browser.get("/api/v1/actions").status_code == 403
    assert browser.get("/api/v1/runs").json()["runs"] == []
    assert browser.get(f"/api/v1/runs/{done['id']}").status_code == 404
    assert browser.get(f"/api/v1/runs/{done['id']}/stream").status_code == 404


def test_unfinished_runs_are_marked_interrupted_on_startup(
    settings: Settings, admin_client: TestClient, database_url: str
) -> None:
    action = _action(admin_client, "true")
    run_id = uuid.uuid4()
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO runs (id, action_id, action_name, args, status, started_at) "
            "VALUES (%s, %s, 'test', '{}', 'running', now())",
            (run_id, action["id"]),
        )
    with TestClient(create_app(settings)):
        pass  # Startup runs recovery.
    run = admin_client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "interrupted"
    assert run["triggered_by"] == "system"


def test_runs_are_listed_in_pages(admin_client: TestClient) -> None:
    first = _action(admin_client, "true")
    second = _action(admin_client, "true", name="other")
    started = [_wait(admin_client, _start(admin_client, first))["id"] for _ in range(5)]
    _wait(admin_client, _start(admin_client, second))

    page1 = admin_client.get("/api/v1/runs", params={"page_size": 4}).json()
    page2 = admin_client.get("/api/v1/runs", params={"page_size": 4, "page": 2}).json()
    assert (page1["total"], page1["page"], page1["page_size"]) == (6, 1, 4)
    assert len(page1["runs"]) == 4
    assert len(page2["runs"]) == 2
    ids = [r["id"] for r in page1["runs"] + page2["runs"]]
    assert len(set(ids)) == 6  # No run is on two pages.
    assert page1["runs"][0]["action_id"] == second["id"]  # Most recent first.
    past_the_end = admin_client.get("/api/v1/runs", params={"page_size": 4, "page": 3}).json()
    assert (past_the_end["runs"], past_the_end["total"]) == ([], 6)

    # The action filter applies before paging, so older runs of one action are reachable.
    history = admin_client.get(
        "/api/v1/runs", params={"action_id": first["id"], "page_size": 2, "page": 3}
    ).json()
    assert history["total"] == 5
    assert [r["id"] for r in history["runs"]] == [started[0]]

    assert admin_client.get("/api/v1/runs", params={"page": 0}).status_code == 422
    assert admin_client.get("/api/v1/runs", params={"page_size": 201}).status_code == 422


# --- Running again ---------------------------------------------------------


def _rerun(client: TestClient, run: dict) -> object:
    return client.post(f"/api/v1/runs/{run['id']}/rerun")


def test_a_run_can_be_run_again_with_the_same_arguments(admin_client: TestClient) -> None:
    action = _action(
        admin_client,
        'echo "hello $ARG_NAME"',
        args=[{"name": "name", "type": "string", "pattern": "[a-z]+"}],
        confirm=True,
    )
    first = _wait(admin_client, _start(admin_client, action, {"name": "plex"}))
    detail = admin_client.get(f"/api/v1/runs/{first['id']}").json()
    assert detail["rerun"] == {"confirm": True}

    response = _rerun(admin_client, first)
    assert response.status_code == 202, response.text
    again = _wait(admin_client, response.json())
    assert again["id"] != first["id"]
    assert (again["action_id"], again["args"], again["output"]) == (
        action["id"],
        {"name": "plex"},
        "hello plex\n",
    )


def test_running_again_uses_the_actions_current_arguments(admin_client: TestClient) -> None:
    action = _action(
        admin_client, "true", args=[{"name": "n", "type": "integer", "min": 1, "max": 9}]
    )
    first = _wait(admin_client, _start(admin_client, action, {"n": 5}))
    admin_client.patch(
        f"/api/v1/actions/{action['id']}",
        json={"args": [{"name": "n", "type": "integer", "min": 1, "max": 3}]},
    )
    response = _rerun(admin_client, first)
    assert response.status_code == 400
    assert "n" in response.json()["detail"]


def test_deleted_actions_and_status_checks_cannot_run_again(
    admin_client: TestClient, database_url: str
) -> None:
    action = _action(admin_client, "true")
    first = _wait(admin_client, _start(admin_client, action))
    admin_client.delete(f"/api/v1/actions/{action['id']}")
    assert admin_client.get(f"/api/v1/runs/{first['id']}").json()["rerun"] is None
    response = _rerun(admin_client, first)
    assert response.status_code == 409
    assert "has been deleted" in response.json()["detail"]

    check = uuid.uuid4()
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO runs (id, action_name, args, status, started_at) "
            "VALUES (%s, 'Check web', '{}', 'succeeded', now())",
            (check,),
        )
    response = _rerun(admin_client, {"id": str(check)})
    assert response.status_code == 409
    assert "Status checks" in response.json()["detail"]


def test_members_run_again_only_what_they_can_still_press(
    admin_client: TestClient, make_client: Callable
) -> None:
    member = {"username": "member", "password": "member password 1"}
    member_id = admin_client.post("/api/v1/users", json=member).json()["id"]
    action = _action(admin_client, "echo hi")
    pad = admin_client.post("/api/v1/pads", json={"name": "Home", "member_ids": [member_id]}).json()
    admin_client.post(
        f"/api/v1/pads/{pad['id']}/buttons", json={"action_id": action["id"], "label": "Hi"}
    )
    browser: TestClient = make_client()
    browser.post("/api/v1/auth/login", json=member)
    mine = _wait(browser, _start(browser, action))
    assert browser.get(f"/api/v1/runs/{mine['id']}").json()["rerun"] == {"confirm": False}
    again = _rerun(browser, mine)
    assert again.status_code == 202
    _wait(browser, again.json())

    # Others' runs are not theirs to see, let alone run again.
    admins = _wait(admin_client, _start(admin_client, action))
    assert _rerun(browser, admins).status_code == 404

    # Once the pad is no longer shared with them, neither is running it again.
    admin_client.patch(f"/api/v1/pads/{pad['id']}", json={"member_ids": []})
    assert browser.get(f"/api/v1/runs/{mine['id']}").json()["rerun"] is None
    assert _rerun(browser, mine).status_code == 403
