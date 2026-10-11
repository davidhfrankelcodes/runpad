"""one item per feature instance

Each feature instance now adds exactly one catalog item: one button or one tile. Existing
instances are split: every Action becomes its own instance (item = its feature key), and
every Tile shown on a pad becomes its own instance (item = its State key), with the States
it shows. The first piece keeps the original instance row. Instances with nothing left to
show are deleted.

Revision ID: 7d3e9a1f5c20
Revises: bc2b329cb54b
Create Date: 2026-10-12 09:00:00.000000+00:00

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7d3e9a1f5c20"
down_revision: str | None = "bc2b329cb54b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("feature_instances", sa.Column("item", sa.String(length=64), nullable=True))
    db = op.get_bind()
    instances = db.execute(
        sa.text("SELECT id FROM feature_instances ORDER BY created_at")
    ).scalars()
    for instance_id in list(instances):
        actions = db.execute(
            sa.text(
                "SELECT id, feature_key, name FROM actions "
                "WHERE feature_instance_id = :i ORDER BY created_at"
            ),
            {"i": instance_id},
        ).all()
        # One piece per State key shown on a pad, named after its tile.
        tiles = db.execute(
            sa.text(
                "SELECT state_key, min(label) FROM tiles WHERE feature_instance_id = :i "
                "GROUP BY state_key ORDER BY state_key"
            ),
            {"i": instance_id},
        ).all()
        pieces = [("action", a_id, key, name) for a_id, key, name in actions] + [
            ("tile", None, key, label) for key, label in tiles
        ]
        if not pieces:
            db.execute(sa.text("DELETE FROM feature_instances WHERE id = :i"), {"i": instance_id})
            continue
        for index, (kind, action_id, key, name) in enumerate(pieces):
            if index == 0:
                target = instance_id
                db.execute(
                    sa.text("UPDATE feature_instances SET item = :k, name = :n WHERE id = :i"),
                    {"k": key, "n": name[:64], "i": instance_id},
                )
            else:
                target = uuid.uuid4()
                db.execute(
                    sa.text(
                        "INSERT INTO feature_instances (id, feature_id, item, name, config) "
                        "SELECT :t, feature_id, :k, :n, config FROM feature_instances "
                        "WHERE id = :i"
                    ),
                    {"t": target, "k": key, "n": name[:64], "i": instance_id},
                )
            if kind == "action":
                db.execute(
                    sa.text("UPDATE actions SET feature_instance_id = :t WHERE id = :a"),
                    {"t": target, "a": action_id},
                )
            else:
                db.execute(
                    sa.text(
                        "UPDATE tiles SET feature_instance_id = :t "
                        "WHERE feature_instance_id = :i AND state_key = :k"
                    ),
                    {"t": target, "i": instance_id, "k": key},
                )
                db.execute(
                    sa.text(
                        "UPDATE states SET feature_instance_id = :t "
                        "WHERE feature_instance_id = :i AND key = :k"
                    ),
                    {"t": target, "i": instance_id, "k": key},
                )
        # States no tile shows any more.
        keep = pieces[0][2] if pieces[0][0] == "tile" else None
        db.execute(
            sa.text(
                "DELETE FROM states WHERE feature_instance_id = :i "
                "AND (CAST(:k AS varchar) IS NULL OR key <> :k)"
            ),
            {"i": instance_id, "k": keep},
        )
    op.alter_column("feature_instances", "item", nullable=False)


def downgrade() -> None:
    # Split instances stay split; each still owns what it generated.
    op.drop_column("feature_instances", "item")
