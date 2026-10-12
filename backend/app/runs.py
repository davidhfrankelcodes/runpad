"""Run history: who ran what, when, and what happened."""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import pads
from app.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Action, Role, Run, User
from app.schemas.runs import RerunInfo, RunDetail, RunPage, RunRead

SYSTEM = "system"


def _visible(user: User) -> Select[tuple[Run, str | None]]:
    query = select(Run, User.username).outerjoin(User, Run.user_id == User.id)
    if user.role != Role.ADMIN:
        query = query.where(Run.user_id == user.id)
    return query


def to_read(run: Run, username: str | None) -> RunRead:
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
    return RunDetail(**to_read(run, username).model_dump(), output=run.output)


async def list_runs(
    db: AsyncSession,
    user: User,
    *,
    action_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
) -> RunPage:
    query = _visible(user)
    if action_id is not None:
        query = query.where(Run.action_id == action_id)
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    rows = await db.execute(
        query.order_by(Run.started_at.desc(), Run.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return RunPage(
        runs=[to_read(run, username) for run, username in rows.all()],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


async def get_run(db: AsyncSession, user: User, run_id: uuid.UUID) -> tuple[Run, str | None]:
    row = (await db.execute(_visible(user).where(Run.id == run_id))).first()
    if row is None:
        raise NotFoundError("Run not found")
    return row[0], row[1]


def check_can_cancel(user: User, run: Run) -> None:
    if user.role != Role.ADMIN and run.user_id != user.id:
        raise PermissionDeniedError("Only admins and the user who started a run can cancel it")


async def action_to_rerun(db: AsyncSession, user: User, run: Run) -> Action:
    """The Action a Run ran, if the user may run it again with the same arguments: the run
    started an Action that still exists, and the user can run it now."""
    # Deleting an Action keeps its Runs but clears their action_id; status checks never
    # had one, and no user.
    action = await db.get(Action, run.action_id) if run.action_id else None
    if action is None:
        if run.user_id is None:
            raise ConflictError("Status checks cannot be run again")
        raise ConflictError(f"{run.action_name} has been deleted")
    await pads.check_can_run(db, user, action.id)
    return action


async def rerun_info(db: AsyncSession, user: User, run: Run) -> RerunInfo | None:
    """Whether the user can run this Run's Action again, and if it asks first."""
    try:
        action = await action_to_rerun(db, user, run)
    except (ConflictError, PermissionDeniedError):
        return None
    return RerunInfo(confirm=action.confirm)
