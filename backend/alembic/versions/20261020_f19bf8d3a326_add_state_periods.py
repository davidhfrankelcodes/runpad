"""add state periods

Revision ID: f19bf8d3a326
Revises: b40eb57d4846
Create Date: 2026-10-20 01:18:33.311426+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f19bf8d3a326"
down_revision: str | None = "b40eb57d4846"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "state_periods",
        sa.Column("feature_instance_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column(
            "tone",
            sa.Enum(
                "good",
                "warn",
                "bad",
                "neutral",
                "unknown",
                name="statetone",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tone IN ('good', 'warn', 'bad', 'neutral', 'unknown')",
            name=op.f("ck_state_periods_tone"),
        ),
        sa.ForeignKeyConstraint(
            ["feature_instance_id"],
            ["feature_instances.id"],
            name=op.f("fk_state_periods_feature_instance_id_feature_instances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_state_periods")),
    )
    op.create_index(
        "ix_state_periods_instance_key_ended_at",
        "state_periods",
        ["feature_instance_id", "key", "ended_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_state_periods_instance_key_ended_at", table_name="state_periods")
    op.drop_table("state_periods")
