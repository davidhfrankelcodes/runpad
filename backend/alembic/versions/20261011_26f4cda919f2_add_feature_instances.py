"""add feature instances

Revision ID: 26f4cda919f2
Revises: 04568fe731be
Create Date: 2026-10-11 13:27:35.245219+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "26f4cda919f2"
down_revision: str | None = "04568fe731be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "feature_instances",
        sa.Column("feature_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feature_instances")),
    )
    op.add_column("actions", sa.Column("feature_instance_id", sa.Uuid(), nullable=True))
    op.add_column("actions", sa.Column("feature_key", sa.String(length=32), nullable=True))
    op.create_unique_constraint(
        op.f("uq_actions_feature_instance_id"), "actions", ["feature_instance_id", "feature_key"]
    )
    op.create_foreign_key(
        op.f("fk_actions_feature_instance_id_feature_instances"),
        "actions",
        "feature_instances",
        ["feature_instance_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_actions_feature_instance_id_feature_instances"), "actions", type_="foreignkey"
    )
    op.drop_constraint(op.f("uq_actions_feature_instance_id"), "actions", type_="unique")
    op.drop_column("actions", "feature_key")
    op.drop_column("actions", "feature_instance_id")
    op.drop_table("feature_instances")
