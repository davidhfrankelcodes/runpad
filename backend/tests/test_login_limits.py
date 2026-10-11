"""Login rate limiting: per client IP and per username, stored in Postgres."""

from collections.abc import Callable, Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import login_limits
from app.config import Settings
from app.main import create_app
from app.security import CSRF_HEADER, CSRF_HEADER_VALUE
from tests.conftest import ADMIN, plain_url

WRONG = {"username": ADMIN["username"], "password": "not the password"}


@pytest.fixture
def browser_at(settings: Settings) -> Iterator[Callable[[str], TestClient]]:
    """Browsers that appear to come from a given IP."""
    clients: list[TestClient] = []

    def factory(ip: str) -> TestClient:
        client = TestClient(
            create_app(settings, poll=False),
            headers={CSRF_HEADER: CSRF_HEADER_VALUE},
            client=(ip, 50000),
        )
        client.__enter__()
        clients.append(client)
        return client

    yield factory
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def admin_exists(browser_at: Callable[[str], TestClient]) -> None:
    assert browser_at("10.0.0.1").post("/api/v1/setup", json=ADMIN).status_code == 201


def _fail(client: TestClient, times: int, credentials: dict = WRONG) -> None:
    for _ in range(times):
        assert client.post("/api/v1/auth/login", json=credentials).status_code == 401


@pytest.mark.usefixtures("admin_exists")
def test_an_ip_is_blocked_after_too_many_failures(
    browser_at: Callable[[str], TestClient],
) -> None:
    attacker = browser_at("203.0.113.9")
    _fail(attacker, login_limits.MAX_FAILURES_PER_IP)

    # Even the right password is refused now, without being checked.
    response = attacker.post("/api/v1/auth/login", json=ADMIN)
    assert response.status_code == 429
    assert "Too many failed logins" in response.json()["detail"]
    retry_after = int(response.headers["Retry-After"])
    assert 0 < retry_after <= login_limits.WINDOW.total_seconds()

    # Someone else, from another IP, can still log in as the same user.
    assert browser_at("198.51.100.7").post("/api/v1/auth/login", json=ADMIN).status_code == 200


@pytest.mark.usefixtures("admin_exists")
def test_failures_for_unknown_users_count_too(browser_at: Callable[[str], TestClient]) -> None:
    attacker = browser_at("203.0.113.9")
    _fail(attacker, login_limits.MAX_FAILURES_PER_IP, {"username": "ghost", "password": "x"})
    assert attacker.post("/api/v1/auth/login", json=ADMIN).status_code == 429


@pytest.mark.usefixtures("admin_exists")
def test_a_username_is_protected_from_many_ips(
    browser_at: Callable[[str], TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(login_limits, "MAX_FAILURES_PER_USERNAME", 6)
    for n in range(3):
        _fail(browser_at(f"203.0.113.{n}"), 2)
    response = browser_at("198.51.100.7").post("/api/v1/auth/login", json=ADMIN)
    assert response.status_code == 429
    # Other usernames are unaffected.
    member = browser_at("198.51.100.8")
    assert (
        member.post("/api/v1/auth/login", json={"username": "other", "password": "x"}).status_code
        == 401
    )


@pytest.mark.usefixtures("admin_exists")
def test_success_clears_that_ips_failures_for_the_user(
    browser_at: Callable[[str], TestClient],
) -> None:
    user = browser_at("198.51.100.7")
    _fail(user, login_limits.MAX_FAILURES_PER_IP - 1)
    assert user.post("/api/v1/auth/login", json=ADMIN).status_code == 200
    _fail(user, login_limits.MAX_FAILURES_PER_IP - 1)
    assert user.post("/api/v1/auth/login", json=ADMIN).status_code == 200


@pytest.mark.usefixtures("admin_exists")
def test_failures_expire_after_the_window(
    browser_at: Callable[[str], TestClient], database_url: str
) -> None:
    attacker = browser_at("203.0.113.9")
    _fail(attacker, login_limits.MAX_FAILURES_PER_IP)
    assert attacker.post("/api/v1/auth/login", json=ADMIN).status_code == 429
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute(
            "UPDATE login_failures SET created_at = created_at - %s",
            (login_limits.WINDOW,),
        )
    assert attacker.post("/api/v1/auth/login", json=ADMIN).status_code == 200


@pytest.mark.usefixtures("admin_exists")
def test_failed_logins_are_logged_for_fail2ban(
    browser_at: Callable[[str], TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    _fail(browser_at("203.0.113.9"), 1, {"username": "Mallory", "password": "x"})
    assert "Failed login for user 'mallory' from 203.0.113.9" in caplog.text
