import base64
from collections.abc import Callable

import asyncssh
import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import plain_url

TOKEN = "super-secret-token-value"


def _create_text(client: TestClient, name: str = "ha token", value: str = TOKEN) -> dict:
    response = client.post("/api/v1/secrets", json={"name": name, "kind": "text", "value": value})
    assert response.status_code == 201, response.text
    return response.json()


def test_secret_value_is_never_returned(admin_client: TestClient) -> None:
    created = _create_text(admin_client)
    listed = admin_client.get("/api/v1/secrets")
    for body in (str(created), listed.text):
        assert TOKEN not in body
    assert "value" not in created and "ciphertext" not in created


def test_secret_is_encrypted_at_rest(admin_client: TestClient, database_url: str) -> None:
    _create_text(admin_client)
    with psycopg.connect(plain_url(database_url)) as conn:
        [(ciphertext,)] = conn.execute("SELECT ciphertext FROM secrets").fetchall()
    assert TOKEN.encode() not in bytes(ciphertext)


def test_duplicate_name_conflicts(admin_client: TestClient) -> None:
    _create_text(admin_client)
    response = admin_client.post(
        "/api/v1/secrets", json={"name": "ha token", "kind": "text", "value": "x"}
    )
    assert response.status_code == 409


def test_generate_ssh_key_returns_public_key_only(admin_client: TestClient) -> None:
    response = admin_client.post("/api/v1/secrets/generate-ssh-key", json={"name": "runpad key"})
    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "ssh_key"
    assert body["public_key"].startswith("ssh-ed25519 ")
    assert body["public_key"].endswith(" runpad")
    assert "PRIVATE KEY" not in response.text


def test_import_ssh_key(admin_client: TestClient) -> None:
    key = asyncssh.generate_private_key("ssh-ed25519")
    response = admin_client.post(
        "/api/v1/secrets",
        json={
            "name": "imported",
            "kind": "ssh_key",
            "value": key.export_private_key("openssh").decode(),
        },
    )
    assert response.status_code == 201
    blob = key.export_public_key("openssh").decode().split()[1]
    assert blob in response.json()["public_key"]


def test_import_rejects_invalid_ssh_key(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/secrets", json={"name": "bad", "kind": "ssh_key", "value": "not a key"}
    )
    assert response.status_code == 400


def _encrypted_openssh_key() -> str:
    """The header of a passphrase-protected OpenSSH key (cipher name is not "none")."""

    def field(value: bytes) -> bytes:
        return len(value).to_bytes(4, "big") + value

    blob = b"openssh-key-v1\0" + field(b"aes256-ctr") + field(b"bcrypt") + field(b"salt")
    body = base64.b64encode(blob).decode()
    return f"-----BEGIN OPENSSH PRIVATE KEY-----\n{body}\n-----END OPENSSH PRIVATE KEY-----\n"


@pytest.mark.parametrize(
    "encrypted",
    [
        pytest.param(_encrypted_openssh_key(), id="openssh"),
        pytest.param(
            asyncssh.generate_private_key("ssh-ed25519")
            .export_private_key("pkcs8-pem", passphrase="pw")
            .decode(),
            id="pkcs8",
        ),
    ],
)
def test_import_rejects_passphrase_protected_key(admin_client: TestClient, encrypted: str) -> None:
    response = admin_client.post(
        "/api/v1/secrets", json={"name": "locked", "kind": "ssh_key", "value": encrypted}
    )
    assert response.status_code == 400
    assert "Passphrase-protected" in response.json()["detail"]


def test_update_replaces_value_and_renames(admin_client: TestClient, database_url: str) -> None:
    secret = _create_text(admin_client)
    with psycopg.connect(plain_url(database_url)) as conn:
        [(before,)] = conn.execute("SELECT ciphertext FROM secrets").fetchall()
    response = admin_client.patch(
        f"/api/v1/secrets/{secret['id']}", json={"name": "renamed", "value": "new value"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"
    with psycopg.connect(plain_url(database_url)) as conn:
        [(after,)] = conn.execute("SELECT ciphertext FROM secrets").fetchall()
    assert before != after


def test_delete_unused_secret(admin_client: TestClient) -> None:
    secret = _create_text(admin_client)
    assert admin_client.delete(f"/api/v1/secrets/{secret['id']}").status_code == 204
    assert admin_client.get("/api/v1/secrets").json() == []


def test_members_cannot_see_secrets(admin_client: TestClient, make_client: Callable) -> None:
    member = {"username": "member", "password": "member password 1"}
    admin_client.post("/api/v1/users", json=member)
    browser: TestClient = make_client()
    browser.post("/api/v1/auth/login", json=member)
    assert browser.get("/api/v1/secrets").status_code == 403
