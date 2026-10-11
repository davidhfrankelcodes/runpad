"""add states and tiles

Revision ID: 868944d5b771
Revises: 26f4cda919f2
Create Date: 2026-10-11 13:44:56.049386+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "868944d5b771"
down_revision: str | None = "26f4cda919f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "states",
        sa.Column("feature_instance_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column(
            "tone",
            sa.Enum(
                "good", "bad", "neutral", "unknown", name="statetone", native_enum=False, length=16
            ),
            nullable=False,
        ),
        sa.Column("detail", sa.Text(), server_default="", nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
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
            "tone IN ('good', 'bad', 'neutral', 'unknown')", name=op.f("ck_states_tone")
        ),
        sa.ForeignKeyConstraint(
            ["feature_instance_id"],
            ["feature_instances.id"],
            name=op.f("fk_states_feature_instance_id_feature_instances"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_states")),
        sa.UniqueConstraint(
            "feature_instance_id", "key", name=op.f("uq_states_feature_instance_id")
        ),
    )
    op.create_table(
        "tiles",
        sa.Column("pad_id", sa.Uuid(), nullable=False),
        sa.Column("feature_instance_id", sa.Uuid(), nullable=False),
        sa.Column("state_key", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
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
        sa.ForeignKeyConstraint(
            ["feature_instance_id"],
            ["feature_instances.id"],
            name=op.f("fk_tiles_feature_instance_id_feature_instances"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pad_id"], ["pads.id"], name=op.f("fk_tiles_pad_id_pads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tiles")),
    )
    op.create_index(
        op.f("ix_tiles_feature_instance_id"), "tiles", ["feature_instance_id"], unique=False
    )
    op.create_index(op.f("ix_tiles_pad_id"), "tiles", ["pad_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tiles_pad_id"), table_name="tiles")
    op.drop_index(op.f("ix_tiles_feature_instance_id"), table_name="tiles")
    op.drop_table("tiles")
    op.drop_table("states")
