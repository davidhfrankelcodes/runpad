import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import RunStatus
from app.schemas.actions import ArgValue


class RunRead(BaseModel):
    id: uuid.UUID
    action_id: uuid.UUID | None
    action_name: str
    triggered_by: str  # A username, or "system" for State polling.
    args: dict[str, ArgValue]
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    output_truncated: bool
    error: str | None


class RerunInfo(BaseModel):
    confirm: bool = Field(description="The action asks for confirmation before running.")


class RunDetail(RunRead):
    output: str
    rerun: RerunInfo | None = Field(
        default=None,
        description="Set when you can run this action again with the same arguments "
        "(POST /runs/{id}/rerun).",
    )


class RunPage(BaseModel):
    """One page of Runs, most recent first."""

    runs: list[RunRead]
    total: int = Field(description="Runs matching the filter, across all pages.")
    page: int
    page_size: int
