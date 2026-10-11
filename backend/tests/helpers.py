"""API helpers shared by tests."""

import time

from fastapi.testclient import TestClient

from tests.fakes import FakeSshServer


def wait_for_run(client: TestClient, run_id: str) -> dict:
    for _ in range(200):
        run = client.get(f"/api/v1/runs/{run_id}").json()
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def create_ssh_target(
    client: TestClient, server: FakeSshServer, authorized: bool = True, name: str = "box"
) -> dict:
    """An SSH target pointing at the fake server, with a generated key it accepts."""
    key = client.post("/api/v1/secrets/generate-ssh-key", json={"name": f"{name} key"}).json()
    if authorized:
        server.authorize(key["public_key"])
    response = client.post(
        "/api/v1/targets",
        json={
            "kind": "ssh",
            "name": name,
            "secret_id": key["id"],
            "config": {
                "host": "127.0.0.1",
                "port": server.port,
                "username": "runpad",
                "host_key": server.host_key_line,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def enable_feature(
    client: TestClient, feature_id: str, config: dict, pad_id: str | None = None, *, item: str
) -> dict:
    """Add one item (a button or a tile) of a feature."""
    response = client.post(
        "/api/v1/feature-instances",
        json={"feature_id": feature_id, "item": item, "config": config, "pad_id": pad_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def managed_actions(client: TestClient, instance: dict) -> dict[str, dict]:
    """The instance's Actions, by name."""
    actions = client.get("/api/v1/actions").json()
    return {a["name"]: a for a in actions if a["feature_instance_id"] == instance["id"]}


def run_and_wait(client: TestClient, action: dict) -> dict:
    response = client.post(f"/api/v1/actions/{action['id']}/run", json={"args": {}})
    assert response.status_code == 202, response.text
    return wait_for_run(client, response.json()["id"])
