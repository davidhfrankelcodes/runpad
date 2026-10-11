"""add warn state tone

Revision ID: 5e0a1c7d2b94
Revises: ca681691a8bd
Create Date: 2026-10-11 19:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "5e0a1c7d2b94"
down_revision: str | None = "ca681691a8bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_states_tone"), "states", type_="check")
    op.create_check_constraint(
        op.f("ck_states_tone"), "states", "tone IN ('good', 'warn', 'bad', 'neutral', 'unknown')"
    )


def downgrade() -> None:
    op.execute("UPDATE states SET tone = 'neutral' WHERE tone = 'warn'")
    op.drop_constraint(op.f("ck_states_tone"), "states", type_="check")
    op.create_check_constraint(
        op.f("ck_states_tone"), "states", "tone IN ('good', 'bad', 'neutral', 'unknown')"
    )
