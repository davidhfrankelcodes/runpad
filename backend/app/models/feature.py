from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class FeatureInstance(TimestampedModel):
    """One catalog item the admin added and configured: a single button (one Action) or a
    single tile (one State key). Owns what it generated; deleting it deletes them."""

    __tablename__ = "feature_instances"

    # The id of a Feature registered in app.features.
    feature_id: Mapped[str] = mapped_column(String(64))
    # The key of one of the Feature's CatalogItems.
    item: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(64))
    # Validated by the Feature's ConfigModel.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
