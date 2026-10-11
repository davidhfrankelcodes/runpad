"""Add secrets and targets

Revision ID: 31d07f1dce0e
Revises: 8fc680c368c0
Create Date: 2026-10-11 01:49:48.235419+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "31d07f1dce0e"
down_revision: str | None = "8fc680c368c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("ssh_key", "text", name="secretkind", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=True),
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
        sa.CheckConstraint("kind IN ('ssh_key', 'text')", name=op.f("ck_secrets_kind")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_secrets")),
        sa.UniqueConstraint("name", name=op.f("uq_secrets_name")),
    )
    op.create_table(
        "targets",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("ssh", "http", name="targetkind", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column("secret_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint("kind IN ('ssh', 'http')", name=op.f("ck_targets_kind")),
        sa.ForeignKeyConstraint(
            ["secret_id"],
            ["secrets.id"],
            name=op.f("fk_targets_secret_id_secrets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_targets")),
        sa.UniqueConstraint("name", name=op.f("uq_targets_name")),
    )
    op.create_index(op.f("ix_targets_secret_id"), "targets", ["secret_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_targets_secret_id"), table_name="targets")
    op.drop_table("targets")
    op.drop_table("secrets")
