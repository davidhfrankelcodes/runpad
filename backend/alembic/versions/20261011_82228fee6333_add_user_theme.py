"""add user theme

Revision ID: 82228fee6333
Revises: 868944d5b771
Create Date: 2026-10-11 14:38:34.643644+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "82228fee6333"
down_revision: str | None = "868944d5b771"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("theme", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "theme")
