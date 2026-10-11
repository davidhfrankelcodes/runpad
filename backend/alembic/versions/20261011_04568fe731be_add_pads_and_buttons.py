"""Add pads and buttons

Revision ID: 04568fe731be
Revises: 3b41ad37ee1b
Create Date: 2026-10-11 02:27:55.729349+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "04568fe731be"
down_revision: str | None = "3b41ad37ee1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pads",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("member_ids", postgresql.ARRAY(sa.Uuid()), server_default="{}", nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pads")),
    )
    op.create_table(
        "buttons",
        sa.Column("pad_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column(
            "color",
            sa.Enum(
                "slate",
                "emerald",
                "sky",
                "amber",
                "red",
                "violet",
                name="buttoncolor",
                native_enum=False,
                length=16,
            ),
            server_default="slate",
            nullable=False,
        ),
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
        sa.CheckConstraint(
            "color IN ('slate', 'emerald', 'sky', 'amber', 'red', 'violet')",
            name=op.f("ck_buttons_color"),
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["actions.id"],
            name=op.f("fk_buttons_action_id_actions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pad_id"], ["pads.id"], name=op.f("fk_buttons_pad_id_pads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_buttons")),
    )
    op.create_index(op.f("ix_buttons_action_id"), "buttons", ["action_id"], unique=False)
    op.create_index(op.f("ix_buttons_pad_id"), "buttons", ["pad_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_buttons_pad_id"), table_name="buttons")
    op.drop_index(op.f("ix_buttons_action_id"), table_name="buttons")
    op.drop_table("buttons")
    op.drop_table("pads")
