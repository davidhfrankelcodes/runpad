from typing import Literal

from pydantic import BaseModel, Field

# The choices offered for keeping Runs; None keeps them forever.
RetentionDays = Literal[7, 14, 30, 90, 180, 365]


class AppSettingsRead(BaseModel):
    run_retention_days: RetentionDays | None = Field(
        description="Finished runs older than this many days are deleted; null keeps them."
    )


class AppSettingsUpdate(BaseModel):
    run_retention_days: RetentionDays | None = Field(
        description="7, 14, 30, 90, 180, or 365 days; null keeps runs forever."
    )
