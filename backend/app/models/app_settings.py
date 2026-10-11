from sqlalchemy import Boolean, CheckConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedModel

DEFAULT_RUN_RETENTION_DAYS = 30


class AppSettings(TimestampedModel):
    """Instance-wide settings, edited by admins in the UI. There is only ever one row."""

    __tablename__ = "app_settings"
    __table_args__ = (CheckConstraint("singleton", name="singleton"),)

    # Always true and unique, so a second row cannot be inserted.
    singleton: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", unique=True
    )
    # Finished Runs older than this are deleted. None keeps them forever.
    run_retention_days: Mapped[int | None] = mapped_column(
        Integer, default=DEFAULT_RUN_RETENTION_DAYS, server_default=str(DEFAULT_RUN_RETENTION_DAYS)
    )
