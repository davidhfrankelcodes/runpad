from collections.abc import Callable

import psycopg
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security import SESSION_COOKIE, hash_token
from tests.conftest import ADMIN, plain_url


def _db_rows(database_url: str, sql: str) -> list[tuple[object, ...]]:
    with psycopg.connect(plain_url(database_url)) as conn:
        return conn.execute(sql).fetchall()  # type: ignore[arg-type]


# --- First-run setup -------------------------------------------------------


def test_setup_is_required_on_a_fresh_install(client: TestClient) -> None:
    assert client.get("/api/v1/setup").json() == {"required": True}


def test_setup_creates_admin_and_logs_in(client: TestClient) -> None:
    response = client.post("/api/v1/setup", json={**ADMIN, "username": "Admin"})
    assert response.status_code == 201
    assert response.json()["username"] == "admin"
    assert response.json()["role"] == "admin"
    assert client.get("/api/v1/auth/me").json()["username"] == "admin"
    assert client.get("/api/v1/setup").json() == {"required": False}


def test_setup_only_works_once(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/setup", json={"username": "intruder", "password": "x" * 12}
    )
    assert response.status_code == 409


def test_setup_rejects_short_password(client: TestClient) -> None:
    response = client.post("/api/v1/setup", json={"username": "admin", "password": "short"})
    assert response.status_code == 422


def test_setup_rejects_invalid_username(client: TestClient) -> None:
    response = client.post("/api/v1/setup", json={"username": "bad name!", "password": "x" * 12})
    assert response.status_code == 422


# --- Login, logout, sessions ----------------------------------------------


def test_login_sets_http_only_cookie(admin_client: TestClient, make_client: Callable) -> None:
    browser: TestClient = make_client()
    response = browser.post("/api/v1/auth/login", json=ADMIN)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert browser.get("/api/v1/auth/me").status_code == 200


def test_login_is_case_insensitive_on_username(
    admin_client: TestClient, make_client: Callable
) -> None:
    response = make_client().post("/api/v1/auth/login", json={**ADMIN, "username": "ADMIN"})
    assert response.status_code == 200


def test_login_rejects_wrong_password(admin_client: TestClient, make_client: Callable) -> None:
    response = make_client().post("/api/v1/auth/login", json={**ADMIN, "password": "wrong" * 3})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_login_rejects_unknown_user_with_same_message(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "x" * 12})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password"}


def test_me_requires_login(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_forged_cookie_is_rejected(admin_client: TestClient, make_client: Callable) -> None:
    browser: TestClient = make_client()
    browser.cookies.set(SESSION_COOKIE, "not-a-real-token")
    assert browser.get("/api/v1/auth/me").status_code == 401


def test_logout_invalidates_session_server_side(admin_client: TestClient) -> None:
    token = admin_client.cookies[SESSION_COOKIE]
    assert admin_client.post("/api/v1/auth/logout").status_code == 204
    admin_client.cookies.set(SESSION_COOKIE, token)  # replaying the old cookie must fail
    assert admin_client.get("/api/v1/auth/me").status_code == 401


def test_session_tokens_and_passwords_are_not_stored_in_plain_text(
    admin_client: TestClient, database_url: str
) -> None:
    token = admin_client.cookies[SESSION_COOKIE]
    [(token_hash,)] = _db_rows(database_url, "SELECT token_hash FROM sessions")
    assert token_hash == hash_token(token) != token
    [(password_hash,)] = _db_rows(database_url, "SELECT password_hash FROM users")
    assert password_hash.startswith("$argon2id$")


def test_session_expiry_slides_on_use(admin_client: TestClient, database_url: str) -> None:
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute("UPDATE sessions SET expires_at = now() + interval '2 days'")
    response = admin_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert SESSION_COOKIE in response.headers["set-cookie"]
    [(days_left,)] = _db_rows(
        database_url, "SELECT extract(day FROM expires_at - now())::int FROM sessions"
    )
    assert days_left >= 29


def test_expired_session_is_rejected(admin_client: TestClient, database_url: str) -> None:
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute("UPDATE sessions SET expires_at = now() - interval '1 second'")
    assert admin_client.get("/api/v1/auth/me").status_code == 401


# --- CSRF ------------------------------------------------------------------


def test_unsafe_api_requests_require_csrf_header(
    settings: Settings, admin_client: TestClient
) -> None:
    with TestClient(create_app(settings)) as bare:
        bare.cookies = admin_client.cookies
        assert bare.post("/api/v1/auth/logout").status_code == 403
        assert bare.get("/api/v1/auth/me").status_code == 200


# --- Own password ----------------------------------------------------------


def test_change_own_password_logs_out_other_sessions(
    admin_client: TestClient, make_client: Callable
) -> None:
    other: TestClient = make_client()
    other.post("/api/v1/auth/login", json=ADMIN)
    new_password = "a brand new password"
    response = admin_client.post(
        "/api/v1/auth/password",
        json={"current_password": ADMIN["password"], "new_password": new_password},
    )
    assert response.status_code == 204
    assert admin_client.get("/api/v1/auth/me").status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401
    relogin = make_client().post("/api/v1/auth/login", json={**ADMIN, "password": new_password})
    assert relogin.status_code == 200


def test_change_own_password_requires_current_password(admin_client: TestClient) -> None:
    response = admin_client.post(
        "/api/v1/auth/password",
        json={"current_password": "not it at all", "new_password": "a brand new password"},
    )
    assert response.status_code == 400
