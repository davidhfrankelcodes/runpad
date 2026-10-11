from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel


class FeatureInstance(TimestampedModel):
    """A catalog Feature the admin enabled and configured. Owns the Actions it generated
    (and through them, their Buttons); deleting the instance deletes them all."""

    __tablename__ = "feature_instances"

    # The id of a Feature registered in app.features.
    feature_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(64))
    # Validated by the Feature's ConfigModel.
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
