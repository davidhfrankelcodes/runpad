import uuid

import psycopg
from alembic import command

from tests.conftest import alembic_config, plain_url


def test_migrations_downgrade_and_upgrade(database_url: str) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_feature_instances_are_split_into_one_item_each(database_url: str) -> None:
    """An instance that made buttons and tiles becomes one instance per button and per tile
    shown, keeping Buttons, Tiles, States, and Runs attached."""
    config = alembic_config(database_url)
    command.downgrade(config, "bc2b329cb54b")
    instance, empty = uuid.uuid4(), uuid.uuid4()
    pad, start, stop, run = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO feature_instances (id, feature_id, name, config) VALUES "
            "(%s, 'docker_container', 'web', '{\"container\": \"web\"}'), "
            "(%s, 'ping_check', 'nothing shown', '{\"host\": \"x\"}')",
            (instance, empty),
        )
        conn.execute("INSERT INTO pads (id, name) VALUES (%s, 'Home')", (pad,))
        for action_id, key, name in ((start, "start", "Start web"), (stop, "stop", "Stop web")):
            conn.execute(
                "INSERT INTO actions (id, name, executor, spec, args, secret_env, "
                "timeout_seconds, concurrency, confirm, feature_instance_id, feature_key) "
                "VALUES (%s, %s, 'ssh', '{}', '[]', '[]', 60, 'reject', false, %s, %s)",
                (action_id, name, instance, key),
            )
            conn.execute(
                "INSERT INTO buttons (id, pad_id, action_id, label) VALUES (%s, %s, %s, %s)",
                (uuid.uuid4(), pad, action_id, name),
            )
        conn.execute(
            "INSERT INTO tiles (id, pad_id, feature_instance_id, state_key, label) "
            "VALUES (%s, %s, %s, 'status', 'web')",
            (uuid.uuid4(), pad, instance),
        )
        conn.execute(
            "INSERT INTO states (id, feature_instance_id, key, value, tone, detail, "
            "checked_at, changed_at) "
            "VALUES (%s, %s, 'status', 'running', 'good', '', now(), now())",
            (uuid.uuid4(), instance),
        )
        conn.execute(
            "INSERT INTO runs (id, action_id, action_name, args, status, started_at) "
            "VALUES (%s, %s, 'Stop web', '{}', 'succeeded', now())",
            (run, stop),
        )

    command.upgrade(config, "head")
    with psycopg.connect(plain_url(database_url)) as conn:
        rows = conn.execute(
            "SELECT id, feature_id, item, name, config FROM feature_instances ORDER BY name"
        ).fetchall()
        assert [(r[1], r[2], r[3]) for r in rows] == [
            ("docker_container", "start", "Start web"),
            ("docker_container", "stop", "Stop web"),
            ("docker_container", "status", "web"),
        ]
        assert all(r[4] == {"container": "web"} for r in rows)
        by_item = {r[2]: r[0] for r in rows}
        assert by_item["start"] == instance  # The first piece keeps the original row.
        owners = dict(conn.execute("SELECT feature_key, feature_instance_id FROM actions"))
        assert owners == {"start": by_item["start"], "stop": by_item["stop"]}
        assert conn.execute("SELECT count(*) FROM buttons").fetchone() == (2,)
        assert conn.execute("SELECT feature_instance_id FROM tiles").fetchall() == [
            (by_item["status"],)
        ]
        assert conn.execute("SELECT feature_instance_id, value FROM states").fetchall() == [
            (by_item["status"], "running")
        ]
        assert conn.execute("SELECT action_id FROM runs").fetchall() == [(stop,)]
        # An instance that showed nothing anywhere is gone.
        assert empty not in by_item.values()
        conn.execute("TRUNCATE feature_instances, pads, actions, runs CASCADE")
        conn.commit()


def test_pads_get_one_board_order_with_tiles_first(database_url: str) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "7d3e9a1f5c20")
    pad, instance = uuid.uuid4(), uuid.uuid4()
    buttons, tiles = [uuid.uuid4(), uuid.uuid4()], [uuid.uuid4(), uuid.uuid4()]
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn:
        conn.execute("INSERT INTO pads (id, name) VALUES (%s, 'Home')", (pad,))
        conn.execute(
            "INSERT INTO feature_instances (id, feature_id, item, name, config) "
            "VALUES (%s, 'ping_check', 'ping', 'db', '{}')",
            (instance,),
        )
        for position, button in enumerate(buttons):
            action = uuid.uuid4()
            conn.execute(
                "INSERT INTO actions (id, name, executor, spec, args, secret_env, "
                "timeout_seconds, concurrency, confirm) "
                "VALUES (%s, 'a', 'local', '{}', '[]', '[]', 30, 'reject', false)",
                (action,),
            )
            conn.execute(
                "INSERT INTO buttons (id, pad_id, action_id, label, position) "
                "VALUES (%s, %s, %s, 'b', %s)",
                (button, pad, action, position),
            )
        for position, tile in enumerate(tiles):
            conn.execute(
                "INSERT INTO tiles (id, pad_id, feature_instance_id, state_key, label, "
                "position) VALUES (%s, %s, %s, 'ping', 't', %s)",
                (tile, pad, instance, position),
            )
    command.upgrade(config, "head")
    with psycopg.connect(plain_url(database_url)) as conn:
        positions = dict(
            conn.execute(
                "SELECT id, position FROM tiles UNION ALL SELECT id, position FROM buttons"
            ).fetchall()
        )
        assert [positions[i] for i in [*tiles, *buttons]] == [0, 1, 2, 3]
        conn.execute("TRUNCATE feature_instances, pads, actions CASCADE")
        conn.commit()
