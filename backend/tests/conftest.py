import os

import psycopg
import pytest
from sqlalchemy.engine import make_url

from app.config import Settings

TEST_SECRET_KEY = "test-secret-key-" + "x" * 32


@pytest.fixture(scope="session")
def database_url() -> str:
    """A freshly recreated test database on the compose `db` service."""
    url = make_url(os.environ["TEST_DATABASE_URL"])
    admin_url = url.set(drivername="postgresql", database="postgres")
    with psycopg.connect(admin_url.render_as_string(hide_password=False), autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{url.database}"')
    return url.render_as_string(hide_password=False)


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(DATABASE_URL=database_url, RUNPAD_SECRET_KEY=TEST_SECRET_KEY)
