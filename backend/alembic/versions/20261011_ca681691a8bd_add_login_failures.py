"""add login failures

Revision ID: ca681691a8bd
Revises: 82228fee6333
Create Date: 2026-10-11 15:05:55.257018+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ca681691a8bd"
down_revision: str | None = "82228fee6333"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "login_failures",
        sa.Column("username", sa.String(length=32), nullable=False),
        sa.Column("ip", sa.String(length=45), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_login_failures")),
    )
    op.create_index(
        "ix_login_failures_ip_created_at", "login_failures", ["ip", "created_at"], unique=False
    )
    op.create_index(
        "ix_login_failures_username_created_at",
        "login_failures",
        ["username", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_login_failures_username_created_at", table_name="login_failures")
    op.drop_index("ix_login_failures_ip_created_at", table_name="login_failures")
    op.drop_table("login_failures")
