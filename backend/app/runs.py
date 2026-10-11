"""Run history: who ran what, when, and what happened."""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError, PermissionDeniedError
from app.models import Role, Run, User
from app.schemas.runs import RunDetail, RunRead

SYSTEM = "system"


def _visible(user: User) -> Select[tuple[Run, str | None]]:
    query = select(Run, User.username).outerjoin(User, Run.user_id == User.id)
    if user.role != Role.ADMIN:
        query = query.where(Run.user_id == user.id)
    return query


def _read(run: Run, username: str | None) -> RunRead:
    return RunRead(
        id=run.id,
        action_id=run.action_id,
        action_name=run.action_name,
        triggered_by=username or SYSTEM,
        args=run.args,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        exit_code=run.exit_code,
        output_truncated=run.output_truncated,
        error=run.error,
    )


def to_detail(run: Run, username: str | None) -> RunDetail:
    return RunDetail(**_read(run, username).model_dump(), output=run.output)


async def list_runs(
    db: AsyncSession, user: User, *, action_id: uuid.UUID | None = None, limit: int = 50
) -> list[RunRead]:
    query = _visible(user).order_by(Run.started_at.desc()).limit(limit)
    if action_id is not None:
        query = query.where(Run.action_id == action_id)
    return [_read(run, username) for run, username in (await db.execute(query)).all()]


async def get_run(db: AsyncSession, user: User, run_id: uuid.UUID) -> tuple[Run, str | None]:
    row = (await db.execute(_visible(user).where(Run.id == run_id))).first()
    if row is None:
        raise NotFoundError("Run not found")
    return row[0], row[1]


def check_can_cancel(user: User, run: Run) -> None:
    if user.role != Role.ADMIN and run.user_id != user.id:
        raise PermissionDeniedError("Only admins and the user who started a run can cancel it")
