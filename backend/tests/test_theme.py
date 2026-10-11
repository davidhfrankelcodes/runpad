"""theme.park integration: each user's theme, and where themes are loaded from."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.security import CSRF_HEADER, CSRF_HEADER_VALUE
from tests.conftest import TEST_SECRET_KEY


def test_users_start_with_runpads_own_colors(admin_client: TestClient) -> None:
    assert admin_client.get("/api/v1/auth/me").json()["theme"] is None


@pytest.mark.parametrize(
    "theme", ["theme-options/nord", "community-theme-options/catppuccin-latte"]
)
def test_users_choose_and_clear_a_theme(admin_client: TestClient, theme: str) -> None:
    response = admin_client.put("/api/v1/auth/theme", json={"theme": theme})
    assert response.status_code == 200, response.text
    assert admin_client.get("/api/v1/auth/me").json()["theme"] == theme

    assert admin_client.put("/api/v1/auth/theme", json={"theme": None}).json()["theme"] is None


@pytest.mark.parametrize(
    "theme",
    [
        "nord",
        "theme-options/Nord",
        "theme-options/../../evil",
        "base/runpad/nord",
        "theme-options/nord.css",
        "https://evil.example/x",
    ],
)
def test_themes_must_be_theme_park_theme_names(admin_client: TestClient, theme: str) -> None:
    assert admin_client.put("/api/v1/auth/theme", json={"theme": theme}).status_code == 422


def test_members_choose_their_own_theme(
    admin_client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    member = {"username": "member", "password": "member password 123"}
    admin_client.post("/api/v1/users", json=member)
    browser = make_client()
    browser.post("/api/v1/auth/login", json=member)
    browser.put("/api/v1/auth/theme", json={"theme": "theme-options/dracula"})
    assert browser.get("/api/v1/auth/me").json()["theme"] == "theme-options/dracula"
    assert admin_client.get("/api/v1/auth/me").json()["theme"] is None


def test_choosing_a_theme_needs_login(client: TestClient) -> None:
    response = client.put("/api/v1/auth/theme", json={"theme": "theme-options/nord"})
    assert response.status_code == 401


def test_appearance_is_public_and_defaults_to_theme_park_dev(client: TestClient) -> None:
    assert client.get("/api/v1/appearance").json() == {"themepark_url": "https://theme-park.dev"}


def test_appearance_uses_a_self_hosted_theme_park(database_url: str) -> None:
    settings = Settings(
        DATABASE_URL=database_url,
        RUNPAD_SECRET_KEY=TEST_SECRET_KEY,
        RUNPAD_THEMEPARK_URL="http://themepark.lan:8080/tp/",
    )
    app = create_app(settings, poll=False)
    with TestClient(app, headers={CSRF_HEADER: CSRF_HEADER_VALUE}) as client:
        url = client.get("/api/v1/appearance").json()["themepark_url"]
    assert url == "http://themepark.lan:8080/tp"


@pytest.mark.parametrize("url", ["theme-park.dev", "ftp://theme-park.dev", "javascript:alert(1)"])
def test_themepark_url_must_be_http(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(DATABASE_URL="x", RUNPAD_SECRET_KEY=TEST_SECRET_KEY, RUNPAD_THEMEPARK_URL=url)
