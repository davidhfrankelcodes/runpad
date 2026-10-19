"""index runs by action and start time

Revision ID: b40eb57d4846
Revises: a41f2c6e9b70
Create Date: 2026-10-19 23:08:14.425321+00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b40eb57d4846"
down_revision: str | None = "a41f2c6e9b70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index(op.f("ix_runs_action_id"), table_name="runs")
    op.create_index(
        "ix_runs_action_id_started_at", "runs", ["action_id", "started_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_runs_action_id_started_at", table_name="runs")
    op.create_index(op.f("ix_runs_action_id"), "runs", ["action_id"], unique=False)
