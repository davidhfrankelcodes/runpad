"""one board order per pad

Buttons and tiles on a pad now share one order, the board's. Existing pads keep how they
looked: their tiles first, then their buttons, each in their previous order.

Revision ID: a41f2c6e9b70
Revises: 7d3e9a1f5c20
Create Date: 2026-10-12 19:00:00.000000+00:00

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a41f2c6e9b70"
down_revision: str | None = "7d3e9a1f5c20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NUMBERED = """
WITH items AS (
    SELECT id, pad_id, 0 AS rank, position, created_at, 'tile' AS kind FROM tiles
    UNION ALL
    SELECT id, pad_id, 1 AS rank, position, created_at, 'button' AS kind FROM buttons
), numbered AS (
    SELECT id, kind,
           row_number() OVER (PARTITION BY pad_id ORDER BY rank, position, created_at) - 1
               AS board_position
    FROM items
)
"""


def upgrade() -> None:
    for table, kind in (("tiles", "tile"), ("buttons", "button")):
        op.execute(
            f"{_NUMBERED} UPDATE {table} AS t SET position = n.board_position "  # noqa: S608
            f"FROM numbered n WHERE n.kind = '{kind}' AND n.id = t.id"
        )


def downgrade() -> None:
    # Positions in one shared order still sort each table correctly on its own.
    pass
