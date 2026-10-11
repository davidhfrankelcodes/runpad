import uuid

from fastapi import APIRouter, status

from app import actions
from app.api.deps import AdminUser, CurrentUser, DbSession, RunnerDep
from app.errors import PermissionDeniedError
from app.models import Role
from app.runs import to_detail
from app.schemas.actions import ActionCreate, ActionRead, ActionUpdate, RunRequest
from app.schemas.runs import RunDetail

router = APIRouter(prefix="/actions", tags=["actions"])


@router.get("")
async def list_actions(_: AdminUser, db: DbSession) -> list[ActionRead]:
    return [ActionRead.model_validate(a) for a in await actions.list_actions(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_action(body: ActionCreate, _: AdminUser, db: DbSession) -> ActionRead:
    return ActionRead.model_validate(await actions.create_action(db, body))


@router.get("/{action_id}")
async def get_action(action_id: uuid.UUID, _: AdminUser, db: DbSession) -> ActionRead:
    return ActionRead.model_validate(await actions.get_action(db, action_id))


@router.patch("/{action_id}")
async def update_action(
    action_id: uuid.UUID, body: ActionUpdate, _: AdminUser, db: DbSession
) -> ActionRead:
    return ActionRead.model_validate(await actions.update_action(db, action_id, body))


@router.delete("/{action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_action(action_id: uuid.UUID, _: AdminUser, db: DbSession) -> None:
    """Delete an Action. Its Runs stay in the history."""
    await actions.delete_action(db, action_id)


@router.post("/{action_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_action(
    action_id: uuid.UUID, body: RunRequest, user: CurrentUser, db: DbSession, runner: RunnerDep
) -> RunDetail:
    """Start a Run and return it immediately. Follow its output at /runs/{id}/stream."""
    action = await actions.get_action(db, action_id)
    # Members gain access through the pads they can see (added with pads).
    if user.role != Role.ADMIN:
        raise PermissionDeniedError("You cannot run this action")
    run = await runner.start(db, action, body.args, user)
    return to_detail(run, user.username)
