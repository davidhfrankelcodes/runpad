from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import TEST_SECRET_KEY


def test_healthz_ok_when_database_reachable(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_unavailable_when_database_unreachable() -> None:
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://runpad:wrong@127.0.0.1:1/runpad",
        RUNPAD_SECRET_KEY=TEST_SECRET_KEY,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")
    assert response.status_code == 503


def test_unknown_api_route_is_json_404(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
