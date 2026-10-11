from alembic import command

from tests.conftest import alembic_config


def test_migrations_downgrade_and_upgrade(database_url: str) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
