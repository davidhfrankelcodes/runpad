"""Personal API tokens: creating, using as a bearer token, expiry, and revocation."""

from collections.abc import Callable, Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import plain_url

MEMBER = {"username": "member", "password": "member password 123"}


@pytest.fixture
def curl(settings: Settings) -> Iterator[TestClient]:
    """A script: no cookies, and no X-Requested-With header."""
    with TestClient(create_app(settings, poll=False)) as client:
        yield client


def _create(client: TestClient, name: str = "script", days: int | None = 30) -> dict:
    response = client.post("/api/v1/auth/tokens", json={"name": name, "expires_in_days": days})
    assert response.status_code == 201, response.text
    return response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_token_authenticates_a_script(admin_client: TestClient, curl: TestClient) -> None:
    created = _create(admin_client)
    token = created["token"]
    assert token.startswith("rp_")
    assert len(token) > 40
    assert created["prefix"] == token[:9]
    assert created["expires_at"] is not None

    assert curl.get("/api/v1/auth/me").status_code == 401
    me = curl.get("/api/v1/auth/me", headers=_bearer(token))
    assert me.status_code == 200
    assert me.json()["username"] == "admin"

    # Unsafe requests need no X-Requested-With header with a token.
    action = curl.post(
        "/api/v1/actions",
        headers=_bearer(token),
        json={"name": "hi", "executor": "local", "spec": {"script": "echo hi"}},
    )
    assert action.status_code == 201, action.text
    run = curl.post(
        f"/api/v1/actions/{action.json()['id']}/run", headers=_bearer(token), json={"args": {}}
    )
    assert run.status_code == 202
    assert run.json()["triggered_by"] == "admin"

    # The token itself is never listed again; when it was last used is.
    [listed] = admin_client.get("/api/v1/auth/tokens").json()
    assert "token" not in listed
    assert listed["prefix"] == created["prefix"]
    assert listed["last_used_at"] is not None


def test_tokens_are_stored_hashed(admin_client: TestClient, database_url: str) -> None:
    token = _create(admin_client)["token"]
    with psycopg.connect(plain_url(database_url)) as conn:
        [(stored,)] = conn.execute("SELECT token_hash FROM api_tokens").fetchall()
    assert token not in stored
    assert len(stored) == 64


def test_cookies_are_ignored_when_a_token_is_sent(admin_client: TestClient) -> None:
    # A logged-in browser that sends a bad token is not let in by its cookie.
    response = admin_client.get("/api/v1/auth/me", headers=_bearer("rp_wrong"))
    assert response.status_code == 401
    assert "API token" in response.json()["detail"]
    response = admin_client.get("/api/v1/auth/me", headers={"Authorization": "Basic eDp5"})
    assert response.status_code == 401
    assert "Bearer" in response.json()["detail"]


def test_without_a_token_unsafe_requests_still_need_the_csrf_header(
    admin_client: TestClient,
) -> None:
    response = admin_client.post(
        "/api/v1/pads", json={"name": "x"}, headers={"X-Requested-With": ""}
    )
    assert response.status_code == 403


def test_never_expiring_tokens_and_expiry_choices(admin_client: TestClient) -> None:
    assert _create(admin_client, days=None)["expires_at"] is None
    for days in (7, 30, 90, 365):
        assert _create(admin_client, days=days)["expires_at"] is not None
    response = admin_client.post("/api/v1/auth/tokens", json={"name": "x", "expires_in_days": 10})
    assert response.status_code == 422


def test_expired_tokens_stop_working(
    admin_client: TestClient, curl: TestClient, database_url: str
) -> None:
    token = _create(admin_client, days=7)["token"]
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute("UPDATE api_tokens SET expires_at = now() - interval '1 second'")
    assert curl.get("/api/v1/auth/me", headers=_bearer(token)).status_code == 401


def test_revoked_tokens_stop_working(admin_client: TestClient, curl: TestClient) -> None:
    created = _create(admin_client)
    assert curl.get("/api/v1/auth/me", headers=_bearer(created["token"])).status_code == 200
    assert admin_client.delete(f"/api/v1/auth/tokens/{created['id']}").status_code == 204
    assert curl.get("/api/v1/auth/me", headers=_bearer(created["token"])).status_code == 401
    assert admin_client.get("/api/v1/auth/tokens").json() == []


def test_a_token_cannot_manage_tokens_or_the_password(
    admin_client: TestClient, curl: TestClient
) -> None:
    created = _create(admin_client)
    auth = _bearer(created["token"])
    assert curl.get("/api/v1/auth/tokens", headers=auth).status_code == 403
    assert curl.post("/api/v1/auth/tokens", headers=auth, json={"name": "x"}).status_code == 403
    assert curl.delete(f"/api/v1/auth/tokens/{created['id']}", headers=auth).status_code == 403
    response = curl.post(
        "/api/v1/auth/password",
        headers=auth,
        json={"current_password": "x", "new_password": "a new password 123"},
    )
    assert response.status_code == 403


def test_member_tokens_have_member_rights_and_die_with_the_account(
    admin_client: TestClient, make_client: Callable[[], TestClient], curl: TestClient
) -> None:
    member_id = admin_client.post("/api/v1/users", json=MEMBER).json()["id"]
    member = make_client()
    assert member.post("/api/v1/auth/login", json=MEMBER).status_code == 200
    created = _create(member)
    auth = _bearer(created["token"])
    assert curl.get("/api/v1/auth/me", headers=auth).json()["role"] == "member"
    assert curl.get("/api/v1/users", headers=auth).status_code == 403

    # Users only see and revoke their own tokens.
    assert admin_client.get("/api/v1/auth/tokens").json() == []
    assert admin_client.delete(f"/api/v1/auth/tokens/{created['id']}").status_code == 404

    admin_client.patch(f"/api/v1/users/{member_id}", json={"is_active": False})
    assert curl.get("/api/v1/auth/me", headers=auth).status_code == 401


def test_the_api_docs_offer_bearer_tokens(curl: TestClient) -> None:
    schema = curl.get("/api/v1/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert curl.get("/api/v1/docs").status_code == 200


def test_the_api_docs_show_the_real_version(curl: TestClient) -> None:
    from app.version import VERSION

    assert VERSION != "unknown"
    assert curl.get("/api/v1/openapi.json").json()["info"]["version"] == VERSION
