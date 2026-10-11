"""SSH and HTTP actions through the API: creation rules, running, and redaction."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeHttpServer, FakeSshServer, fake_ssh_server
from tests.helpers import create_ssh_target, wait_for_run


@pytest.fixture
def ssh_server() -> Iterator[FakeSshServer]:
    with fake_ssh_server() as server:
        yield server


def _http_target(client: TestClient, url: str, token: str | None = None) -> dict:
    secret_id = None
    if token:
        secret_id = client.post(
            "/api/v1/secrets", json={"name": "tok", "kind": "text", "value": token}
        ).json()["id"]
    response = client.post(
        "/api/v1/targets",
        json={"kind": "http", "name": "api", "secret_id": secret_id, "config": {"base_url": url}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create(client: TestClient, body: dict) -> dict:
    response = client.post("/api/v1/actions", json={"name": "remote", **body})
    assert response.status_code == 201, response.text
    return response.json()


def _run(client: TestClient, action: dict, args: dict | None = None) -> dict:
    response = client.post(f"/api/v1/actions/{action['id']}/run", json={"args": args or {}})
    assert response.status_code == 202, response.text
    return wait_for_run(client, response.json()["id"])


def test_ssh_action_runs_on_the_target(admin_client: TestClient, ssh_server: FakeSshServer) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    action = _create(
        admin_client,
        {
            "executor": "ssh",
            "target_id": target["id"],
            "spec": {"script": 'echo "restarting $ARG_SERVICE"; exit 3'},
            "args": [{"name": "service", "type": "string", "pattern": "[a-z]+"}],
        },
    )
    run = _run(admin_client, action, {"service": "nginx"})
    assert (run["status"], run["exit_code"], run["output"]) == ("failed", 3, "restarting nginx\n")


def test_ssh_secret_variables_are_redacted(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    secret = admin_client.post(
        "/api/v1/secrets", json={"name": "pw", "kind": "text", "value": "hunter2-hunter2"}
    ).json()
    action = _create(
        admin_client,
        {
            "executor": "ssh",
            "target_id": target["id"],
            "spec": {"script": 'echo "pw=$PW"'},
            "secret_env": [{"name": "PW", "secret_id": secret["id"]}],
        },
    )
    assert _run(admin_client, action)["output"] == "pw=[redacted]\n"
    assert "hunter2" not in ssh_server.commands[-1]


def test_ssh_connection_failure_is_reported(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server, authorized=False)
    action = _create(
        admin_client, {"executor": "ssh", "target_id": target["id"], "spec": {"script": "true"}}
    )
    run = _run(admin_client, action)
    assert run["status"] == "failed"
    assert run["exit_code"] is None
    assert "Authentication failed" in run["error"]


def test_ssh_timeout_marks_run_timed_out(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = create_ssh_target(admin_client, ssh_server)
    action = _create(
        admin_client,
        {
            "executor": "ssh",
            "target_id": target["id"],
            "spec": {"script": "echo started; sleep 30"},
            "timeout_seconds": 1,
        },
    )
    run = _run(admin_client, action)
    assert (run["status"], run["output"]) == ("timed_out", "started\n")


def test_http_action_fills_placeholders_and_redacts_token(admin_client: TestClient) -> None:
    with FakeHttpServer(required_token="tok-123456") as server:
        target = _http_target(admin_client, server.url + "api/", token="tok-123456")
        action = _create(
            admin_client,
            {
                "executor": "http",
                "target_id": target["id"],
                "spec": {
                    "method": "POST",
                    "path": "services/{domain}/turn_on",
                    "body": {"entity_id": "{entity}", "brightness": "{level}"},
                },
                "args": [
                    {"name": "domain", "type": "enum", "choices": ["light", "switch"]},
                    {"name": "entity", "type": "string", "pattern": "[a-z_.]+"},
                    {"name": "level", "type": "integer", "min": 0, "max": 255, "default": 128},
                ],
            },
        )
        run = _run(admin_client, action, {"domain": "light", "entity": "light.desk"})
    assert run["status"] == "succeeded"
    assert run["exit_code"] == 0
    assert run["output"].startswith("HTTP 200 OK\n")
    # The fake echoes the Authorization header; the token must not reach the output.
    assert "tok-123456" not in run["output"]
    assert "Bearer [redacted]" in run["output"]
    [request] = server.requests
    assert request["path"] == "/api/services/light/turn_on"
    assert request["body"] == {"entity_id": "light.desk", "brightness": 128}


def test_http_error_status_fails_the_run(admin_client: TestClient) -> None:
    with FakeHttpServer(status=500) as server:
        target = _http_target(admin_client, server.url)
        action = _create(
            admin_client,
            {"executor": "http", "target_id": target["id"], "spec": {"method": "GET"}},
        )
        run = _run(admin_client, action)
    assert (run["status"], run["exit_code"]) == ("failed", 500)


def test_executor_and_target_kind_must_match(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    ssh_target = create_ssh_target(admin_client, ssh_server)
    response = admin_client.post(
        "/api/v1/actions",
        json={"name": "x", "executor": "http", "target_id": ssh_target["id"], "spec": {}},
    )
    assert response.status_code == 400
    assert "needs a http target" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {"executor": "ssh", "spec": {"script": "true"}},  # No target.
        {"executor": "local", "spec": {"method": "GET"}},  # Wrong spec for executor.
        {
            "executor": "http",
            "target_id": "00000000-0000-0000-0000-000000000000",
            "spec": {"path": "x/{missing}"},
        },
        {
            "executor": "http",
            "target_id": "00000000-0000-0000-0000-000000000000",
            "spec": {},
            "secret_env": [{"name": "TOKEN", "secret_id": "00000000-0000-0000-0000-000000000000"}],
        },
    ],
)
def test_invalid_action_definitions_are_rejected(admin_client: TestClient, body: dict) -> None:
    assert admin_client.post("/api/v1/actions", json={"name": "x", **body}).status_code == 422


def test_update_rejects_placeholder_for_removed_argument(admin_client: TestClient) -> None:
    with FakeHttpServer() as server:
        target = _http_target(admin_client, server.url)
    action = _create(
        admin_client,
        {
            "executor": "http",
            "target_id": target["id"],
            "spec": {"path": "x/{id}"},
            "args": [{"name": "id", "type": "integer", "min": 1, "max": 9}],
        },
    )
    response = admin_client.patch(f"/api/v1/actions/{action['id']}", json={"args": []})
    assert response.status_code == 400
    assert "Unknown placeholders: id" in response.json()["detail"]


def test_target_in_use_cannot_be_deleted(admin_client: TestClient) -> None:
    with FakeHttpServer() as server:
        target = _http_target(admin_client, server.url)
    _create(admin_client, {"executor": "http", "target_id": target["id"], "spec": {}})
    response = admin_client.delete(f"/api/v1/targets/{target['id']}")
    assert response.status_code == 409
    assert "remote" in response.json()["detail"]


def test_where_an_action_runs_can_change(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    ssh_target = create_ssh_target(admin_client, ssh_server)
    action = _create(admin_client, {"executor": "local", "spec": {"script": "echo hi"}})
    url = f"/api/v1/actions/{action['id']}"

    # Local to SSH keeps the script and needs a target of the right kind.
    response = admin_client.patch(url, json={"executor": "ssh"})
    assert response.status_code == 400
    assert "needs a target" in response.json()["detail"]
    response = admin_client.patch(url, json={"executor": "ssh", "target_id": ssh_target["id"]})
    assert response.status_code == 200, response.text
    moved = response.json()
    assert (moved["executor"], moved["target_id"]) == ("ssh", ssh_target["id"])
    assert moved["spec"]["script"] == "echo hi"
    run = _run(admin_client, moved)
    assert (run["status"], run["output"]) == ("succeeded", "hi\n")

    # Switching to HTTP needs a request spec and an HTTP target.
    with FakeHttpServer() as server:
        http_target = _http_target(admin_client, server.url)
        response = admin_client.patch(
            url, json={"executor": "http", "target_id": http_target["id"]}
        )
        assert response.status_code == 400
        assert "needs a new spec" in response.json()["detail"]
        response = admin_client.patch(
            url, json={"executor": "http", "target_id": ssh_target["id"], "spec": {"method": "GET"}}
        )
        assert response.status_code == 400
        response = admin_client.patch(
            url,
            json={"executor": "http", "target_id": http_target["id"], "spec": {"method": "GET"}},
        )
        assert response.status_code == 200, response.text
        assert _run(admin_client, response.json())["status"] == "succeeded"

    # Back to local drops the target.
    response = admin_client.patch(url, json={"executor": "local", "spec": {"script": "true"}})
    assert response.status_code == 200, response.text
    assert (response.json()["executor"], response.json()["target_id"]) == ("local", None)


def test_switching_to_http_rejects_secret_variables(admin_client: TestClient) -> None:
    secret = admin_client.post(
        "/api/v1/secrets", json={"name": "tok", "kind": "text", "value": "s3cret"}
    ).json()
    action = _create(
        admin_client,
        {
            "executor": "local",
            "spec": {"script": "true"},
            "secret_env": [{"name": "TOKEN", "secret_id": secret["id"]}],
        },
    )
    with FakeHttpServer() as server:
        target = _http_target(admin_client, server.url)
    body = {"executor": "http", "target_id": target["id"], "spec": {}}
    response = admin_client.patch(f"/api/v1/actions/{action['id']}", json=body)
    assert response.status_code == 400
    assert "cannot use secret variables" in response.json()["detail"]
    response = admin_client.patch(
        f"/api/v1/actions/{action['id']}", json={**body, "secret_env": []}
    )
    assert response.status_code == 200, response.text
