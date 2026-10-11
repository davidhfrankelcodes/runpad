from collections.abc import Callable

from fastapi.testclient import TestClient

MEMBER = {"username": "member", "password": "member password 123"}


def _create_member(admin_client: TestClient) -> dict:
    response = admin_client.post("/api/v1/users", json=MEMBER)
    assert response.status_code == 201, response.text
    return response.json()


def _login(make_client: Callable, credentials: dict) -> TestClient:
    browser: TestClient = make_client()
    assert browser.post("/api/v1/auth/login", json=credentials).status_code == 200
    return browser


def test_admin_creates_member(admin_client: TestClient, make_client: Callable) -> None:
    member = _create_member(admin_client)
    assert member["role"] == "member"
    assert member["is_active"] is True
    assert "password" not in member and "password_hash" not in member
    names = [u["username"] for u in admin_client.get("/api/v1/users").json()]
    assert names == ["admin", "member"]
    _login(make_client, MEMBER)


def test_duplicate_username_conflicts(admin_client: TestClient) -> None:
    _create_member(admin_client)
    response = admin_client.post("/api/v1/users", json={**MEMBER, "username": "MEMBER"})
    assert response.status_code == 409


def test_member_cannot_manage_users(admin_client: TestClient, make_client: Callable) -> None:
    _create_member(admin_client)
    member = _login(make_client, MEMBER)
    assert member.get("/api/v1/users").status_code == 403
    assert member.post("/api/v1/users", json={**MEMBER, "username": "other"}).status_code == 403


def test_anonymous_cannot_manage_users(admin_client: TestClient, client: TestClient) -> None:
    anonymous = TestClient(client.app, headers=dict(client.headers))
    assert anonymous.get("/api/v1/users").status_code == 401


def test_deactivating_user_logs_them_out_and_blocks_login(
    admin_client: TestClient, make_client: Callable
) -> None:
    member_id = _create_member(admin_client)["id"]
    member = _login(make_client, MEMBER)
    response = admin_client.patch(f"/api/v1/users/{member_id}", json={"is_active": False})
    assert response.status_code == 200
    assert member.get("/api/v1/auth/me").status_code == 401
    assert make_client().post("/api/v1/auth/login", json=MEMBER).status_code == 401


def test_promote_member_to_admin(admin_client: TestClient, make_client: Callable) -> None:
    member_id = _create_member(admin_client)["id"]
    response = admin_client.patch(f"/api/v1/users/{member_id}", json={"role": "admin"})
    assert response.json()["role"] == "admin"
    assert _login(make_client, MEMBER).get("/api/v1/users").status_code == 200


def test_cannot_remove_last_active_admin(admin_client: TestClient) -> None:
    admin_id = admin_client.get("/api/v1/auth/me").json()["id"]
    demote = admin_client.patch(f"/api/v1/users/{admin_id}", json={"role": "member"})
    deactivate = admin_client.patch(f"/api/v1/users/{admin_id}", json={"is_active": False})
    assert demote.status_code == 409
    assert deactivate.status_code == 409


def test_can_demote_admin_when_another_admin_exists(admin_client: TestClient) -> None:
    admin_client.post("/api/v1/users", json={**MEMBER, "role": "admin"})
    admin_id = admin_client.get("/api/v1/auth/me").json()["id"]
    response = admin_client.patch(f"/api/v1/users/{admin_id}", json={"role": "member"})
    assert response.status_code == 200


def test_admin_password_reset_logs_user_out(
    admin_client: TestClient, make_client: Callable
) -> None:
    member_id = _create_member(admin_client)["id"]
    member = _login(make_client, MEMBER)
    new_password = "reset by the admin"
    admin_client.patch(f"/api/v1/users/{member_id}", json={"password": new_password})
    assert member.get("/api/v1/auth/me").status_code == 401
    _login(make_client, {**MEMBER, "password": new_password})


def test_update_unknown_user_is_404(admin_client: TestClient) -> None:
    response = admin_client.patch(
        "/api/v1/users/00000000-0000-0000-0000-000000000000", json={"is_active": False}
    )
    assert response.status_code == 404
