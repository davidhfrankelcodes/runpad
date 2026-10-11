from collections.abc import Iterator

import asyncssh
import pytest
from fastapi.testclient import TestClient

from tests.fakes import (
    FakeHttpServer,
    FakeSshServer,
    fake_ssh_server,
    fake_ssh_server_with_keys,
)


@pytest.fixture
def ssh_server() -> Iterator[FakeSshServer]:
    with fake_ssh_server() as server:
        yield server


def _generate_key(client: TestClient, name: str = "runpad key") -> dict:
    response = client.post("/api/v1/secrets/generate-ssh-key", json={"name": name})
    assert response.status_code == 201
    return response.json()


def _scan(client: TestClient, server: FakeSshServer) -> dict:
    response = client.post(
        "/api/v1/targets/scan-host-key", json={"host": "127.0.0.1", "port": server.port}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _create_ssh_target(client: TestClient, server: FakeSshServer, key: dict) -> dict:
    scanned = _scan(client, server)
    response = client.post(
        "/api/v1/targets",
        json={
            "kind": "ssh",
            "name": "nas",
            "secret_id": key["id"],
            "config": {
                "host": "127.0.0.1",
                "port": server.port,
                "username": "runpad",
                "host_key": scanned["public_key"],
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_scan_returns_server_host_key(admin_client: TestClient, ssh_server: FakeSshServer) -> None:
    scanned = _scan(admin_client, ssh_server)
    assert scanned["public_key"] == ssh_server.host_key_line
    assert scanned["algorithm"] == "ssh-ed25519"
    assert scanned["fingerprint"] == ssh_server.host_key.get_fingerprint("sha256")


def test_scan_prefers_ed25519_over_rsa(admin_client: TestClient) -> None:
    with fake_ssh_server_with_keys("ssh-rsa") as server:
        scanned = _scan(admin_client, server)
    assert scanned["algorithm"] == "ssh-ed25519"
    assert scanned["public_key"] == server.host_key_line


def test_scan_unreachable_host_is_400(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/targets/scan-host-key", json={"host": "127.0.0.1", "port": 1}
    )
    assert response.status_code == 400


def test_create_ssh_target_pins_host_key(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = _create_ssh_target(admin_client, ssh_server, _generate_key(admin_client))
    assert target["kind"] == "ssh"
    assert target["config"]["host_key"] == ssh_server.host_key_line
    assert target["config"]["host_key_fingerprint"].startswith("SHA256:")


def test_connection_succeeds_with_authorized_key(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    key = _generate_key(admin_client)
    ssh_server.authorize(key["public_key"])
    target = _create_ssh_target(admin_client, ssh_server, key)
    result = admin_client.post(f"/api/v1/targets/{target['id']}/test").json()
    assert result == {"ok": True, "message": "Connected and authenticated"}


def test_connection_reports_unauthorized_key(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    target = _create_ssh_target(admin_client, ssh_server, _generate_key(admin_client))
    result = admin_client.post(f"/api/v1/targets/{target['id']}/test").json()
    assert result["ok"] is False
    assert "Authentication failed" in result["message"]


def test_changed_host_key_fails_and_is_never_accepted(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    key = _generate_key(admin_client)
    ssh_server.authorize(key["public_key"])
    target = _create_ssh_target(admin_client, ssh_server, key)
    # Simulate the host being replaced: pin a different key than the server presents.
    impostor = asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh").decode()
    config = {**target["config"], "host_key": impostor}
    del config["host_key_fingerprint"]
    admin_client.patch(f"/api/v1/targets/{target['id']}", json={"config": config})

    result = admin_client.post(f"/api/v1/targets/{target['id']}/test").json()
    assert result["ok"] is False
    assert "does not match the pinned key" in result["message"]
    # Still pinned to the configured key; nothing was auto-accepted.
    pinned = admin_client.get(f"/api/v1/targets/{target['id']}").json()["config"]["host_key"]
    assert pinned == " ".join(impostor.split()[:2])


def test_ssh_target_requires_ssh_key_secret(admin_client: TestClient) -> None:
    text = admin_client.post(
        "/api/v1/secrets", json={"name": "tok", "kind": "text", "value": "x"}
    ).json()
    host_key = asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh").decode()
    response = admin_client.post(
        "/api/v1/targets",
        json={
            "kind": "ssh",
            "name": "nas",
            "secret_id": text["id"],
            "config": {"host": "nas.local", "username": "root", "host_key": host_key},
        },
    )
    assert response.status_code == 400


def test_ssh_target_rejects_invalid_host_key(admin_client: TestClient) -> None:
    key = _generate_key(admin_client)
    response = admin_client.post(
        "/api/v1/targets",
        json={
            "kind": "ssh",
            "name": "nas",
            "secret_id": key["id"],
            "config": {"host": "nas.local", "username": "root", "host_key": "garbage"},
        },
    )
    assert response.status_code == 422


def test_secret_in_use_cannot_be_deleted(
    admin_client: TestClient, ssh_server: FakeSshServer
) -> None:
    key = _generate_key(admin_client)
    target = _create_ssh_target(admin_client, ssh_server, key)
    response = admin_client.delete(f"/api/v1/secrets/{key['id']}")
    assert response.status_code == 409
    assert "nas" in response.json()["detail"]
    assert admin_client.delete(f"/api/v1/targets/{target['id']}").status_code == 204
    assert admin_client.delete(f"/api/v1/secrets/{key['id']}").status_code == 204


def test_http_target_sends_bearer_token(admin_client: TestClient) -> None:
    token = admin_client.post(
        "/api/v1/secrets", json={"name": "tok", "kind": "text", "value": "s3cret"}
    ).json()
    with FakeHttpServer(required_token="s3cret") as server:
        target = admin_client.post(
            "/api/v1/targets",
            json={
                "kind": "http",
                "name": "home assistant",
                "secret_id": token["id"],
                "config": {"base_url": server.url},
            },
        ).json()
        result = admin_client.post(f"/api/v1/targets/{target['id']}/test").json()
        assert result == {"ok": True, "message": "Reachable (HTTP 200)"}

        admin_client.patch(f"/api/v1/targets/{target['id']}", json={"clear_secret": True})
        result = admin_client.post(f"/api/v1/targets/{target['id']}/test").json()
        assert result["ok"] is False
        assert "authentication was rejected" in result["message"]
    assert server.seen_authorization == ["Bearer s3cret", None]


def test_config_must_match_target_kind(admin_client: TestClient) -> None:
    target = admin_client.post(
        "/api/v1/targets",
        json={"kind": "http", "name": "hook", "config": {"base_url": "http://example.test/"}},
    ).json()
    host_key = asyncssh.generate_private_key("ssh-ed25519").export_public_key("openssh").decode()
    response = admin_client.patch(
        f"/api/v1/targets/{target['id']}",
        json={"config": {"host": "nas", "username": "root", "host_key": host_key}},
    )
    assert response.status_code == 400


def test_duplicate_target_name_conflicts(admin_client: TestClient) -> None:
    body = {"kind": "http", "name": "hook", "config": {"base_url": "http://example.test/"}}
    assert admin_client.post("/api/v1/targets", json=body).status_code == 201
    assert admin_client.post("/api/v1/targets", json=body).status_code == 409
