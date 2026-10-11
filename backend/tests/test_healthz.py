from fastapi.testclient import TestClient

from app.config import Settings
from app.db import create_engine
from app.main import create_app


def test_healthz_ok_when_database_reachable(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_unavailable_when_database_goes_away(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        # Simulate the database becoming unreachable after startup.
        client.app.state.engine = create_engine(  # type: ignore[attr-defined]
            "postgresql+psycopg://runpad:wrong@127.0.0.1:1/runpad"
        )
        response = client.get("/healthz")
    assert response.status_code == 503


def test_unknown_api_route_is_json_404(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}
