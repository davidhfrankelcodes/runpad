import os
import socket
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
import uvicorn
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL, make_url

from app.config import Settings
from app.main import create_app
from app.models import Base
from app.security import CSRF_HEADER, CSRF_HEADER_VALUE

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_SECRET_KEY = "test-secret-key-" + "x" * 32
ADMIN = {"username": "admin", "password": "correct horse battery"}


def plain_url(url: str | URL) -> str:
    """A libpq URL for direct psycopg connections (no SQLAlchemy driver suffix)."""
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def alembic_config(database_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config


def run_migrations(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


@pytest.fixture(scope="session")
def database_url() -> str:
    """A freshly recreated, fully migrated test database on the compose `db` service."""
    url = make_url(os.environ["TEST_DATABASE_URL"])
    with psycopg.connect(plain_url(url.set(database="postgres")), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{url.database}"')
    rendered = url.render_as_string(hide_password=False)
    run_migrations(rendered)
    return rendered


@pytest.fixture(autouse=True)
def clean_database(request: pytest.FixtureRequest) -> Iterator[None]:
    """Empty every table after each test that touched the database."""
    yield
    if "database_url" not in request.fixturenames:
        return
    url = request.getfixturevalue("database_url")
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with psycopg.connect(plain_url(url), autocommit=True) as conn:
        conn.execute(f"TRUNCATE {tables} CASCADE")


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(DATABASE_URL=database_url, RUNPAD_SECRET_KEY=TEST_SECRET_KEY)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """An anonymous browser: sends the CSRF header and keeps cookies like the frontend does."""
    with TestClient(
        create_app(settings, poll=False), headers={CSRF_HEADER: CSRF_HEADER_VALUE}
    ) as c:
        yield c


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    """A browser logged in as the first admin, created through setup."""
    response = client.post("/api/v1/setup", json=ADMIN)
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
def make_client(settings: Settings) -> Iterator[Callable[[], TestClient]]:
    """Factory for extra independent browsers (separate cookie jars)."""
    clients: list[TestClient] = []

    def factory() -> TestClient:
        c = TestClient(create_app(settings, poll=False), headers={CSRF_HEADER: CSRF_HEADER_VALUE})
        c.__enter__()
        clients.append(c)
        return c

    yield factory
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def live_url(settings: Settings) -> Iterator[str]:
    """A real server (TestClient buffers streaming responses), with State polling on."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            timeout_graceful_shutdown=2,  # As in production: event streams never end.
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("server did not start")
        time.sleep(0.02)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)
