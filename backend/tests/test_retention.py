"""Run retention: the setting, and deleting finished Runs older than it."""

import asyncio
import uuid
from collections.abc import Callable

import psycopg
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import retention
from app.config import Settings
from app.db import create_engine, create_sessionmaker
from tests.conftest import plain_url

MEMBER = {"username": "member", "password": "member password 123"}


def _insert_run(database_url: str, days_ago: int, status: str = "succeeded") -> uuid.UUID:
    run_id = uuid.uuid4()
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO runs (id, action_name, args, status, started_at) VALUES "
            "(%s, 'old', '{}', %s, now() - make_interval(days => %s))",
            (run_id, status, days_ago),
        )
    return run_id


def _run_ids(database_url: str) -> set[uuid.UUID]:
    with psycopg.connect(plain_url(database_url)) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM runs").fetchall()}


async def _purge(settings: Settings) -> int:
    engine = create_engine(settings.database_url)
    try:
        async with create_sessionmaker(engine)() as db:
            assert isinstance(db, AsyncSession)
            return await retention.purge_runs(db)
    finally:
        await engine.dispose()


def test_runs_are_kept_30_days_by_default(admin_client: TestClient) -> None:
    assert admin_client.get("/api/v1/settings").json() == {"run_retention_days": 30}


def test_old_finished_runs_are_deleted(
    admin_client: TestClient, settings: Settings, database_url: str
) -> None:
    _insert_run(database_url, days_ago=31)
    recent = _insert_run(database_url, days_ago=29)
    stuck = _insert_run(database_url, days_ago=60, status="running")
    assert asyncio.run(_purge(settings)) == 1
    assert _run_ids(database_url) == {recent, stuck}


def test_shortening_retention_deletes_at_once(admin_client: TestClient, database_url: str) -> None:
    week_old = _insert_run(database_url, days_ago=8)
    today = _insert_run(database_url, days_ago=0)
    response = admin_client.put("/api/v1/settings", json={"run_retention_days": 7})
    assert response.status_code == 200
    assert response.json() == {"run_retention_days": 7}
    assert _run_ids(database_url) == {today}
    assert week_old not in _run_ids(database_url)


def test_runs_can_be_kept_forever(
    admin_client: TestClient, settings: Settings, database_url: str
) -> None:
    ancient = _insert_run(database_url, days_ago=3000)
    assert admin_client.put("/api/v1/settings", json={"run_retention_days": None}).json() == {
        "run_retention_days": None
    }
    assert asyncio.run(_purge(settings)) == 0
    assert ancient in _run_ids(database_url)


def test_only_offered_periods_are_accepted(admin_client: TestClient) -> None:
    for days in (0, 10, -1, 1000):
        response = admin_client.put("/api/v1/settings", json={"run_retention_days": days})
        assert response.status_code == 422


def test_members_can_read_but_not_change_retention(
    admin_client: TestClient, make_client: Callable[[], TestClient]
) -> None:
    admin_client.post("/api/v1/users", json=MEMBER)
    member = make_client()
    member.post("/api/v1/auth/login", json=MEMBER)
    assert member.get("/api/v1/settings").json() == {"run_retention_days": 30}
    response = member.put("/api/v1/settings", json={"run_retention_days": 7})
    assert response.status_code == 403
