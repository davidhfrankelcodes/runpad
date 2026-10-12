import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse

from app import runs
from app.api.deps import CurrentUser, DbSession, RunnerDep
from app.errors import ConflictError
from app.schemas.runs import RunDetail, RunPage

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs(
    user: CurrentUser,
    db: DbSession,
    action_id: uuid.UUID | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RunPage:
    """One page of Runs, most recent first. Admins see every Run; members see their own."""
    return await runs.list_runs(db, user, action_id=action_id, page=page, page_size=page_size)


@router.get("/{run_id}")
async def get_run(run_id: uuid.UUID, user: CurrentUser, db: DbSession) -> RunDetail:
    run, username = await runs.get_run(db, user, run_id)
    detail = runs.to_detail(run, username)
    detail.rerun = await runs.rerun_info(db, user, run)
    return detail


@router.post("/{run_id}/rerun", status_code=status.HTTP_202_ACCEPTED)
async def rerun(
    run_id: uuid.UUID, user: CurrentUser, db: DbSession, runner: RunnerDep
) -> RunDetail:
    """Run the same Action again with the arguments this Run used, as you. Refused for
    status checks, deleted actions, actions you cannot run, and arguments the action no
    longer accepts. Confirming first is up to the client, as for any run."""
    run, _ = await runs.get_run(db, user, run_id)
    action = await runs.action_to_rerun(db, user, run)
    started = await runner.start(db, action, run.args, user)
    return runs.to_detail(started, user.username)


@router.post("/{run_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: uuid.UUID, user: CurrentUser, db: DbSession, runner: RunnerDep
) -> None:
    run, _ = await runs.get_run(db, user, run_id)
    runs.check_can_cancel(user, run)
    if not await runner.cancel(run_id):
        raise ConflictError("Run is not in progress")


def _event(name: str, data: object) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


@router.get(
    "/{run_id}/stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_run(
    run_id: uuid.UUID, user: CurrentUser, db: DbSession, runner: RunnerDep
) -> StreamingResponse:
    """Server-Sent Events: `output` events carry text chunks (JSON strings), from the start
    of the Run; a final `end` event carries the finished Run."""
    run, username = await runs.get_run(db, user, run_id)
    active = runner.active(run_id)
    if active is None:
        await db.refresh(run)  # It may have finished since it was loaded.

    async def events() -> AsyncIterator[str]:
        if active is not None:
            async for chunk in active.follow():
                yield ": keepalive\n\n" if chunk is None else _event("output", chunk)
            final, final_user = await runner.load(run_id)
        else:
            if run.output:
                yield _event("output", run.output)
            final, final_user = run, username
        yield _event("end", runs.to_detail(final, final_user).model_dump(mode="json"))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
