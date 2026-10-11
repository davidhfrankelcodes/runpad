"""Actions: stored commands with typed arguments. Runs are started through runner.py."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import DomainError, NotFoundError
from app.models import Action, Executor, Secret, SecretKind
from app.schemas.actions import ActionCreate, ActionUpdate, SecretEnv


async def _check_secrets(db: AsyncSession, secret_env: list[SecretEnv]) -> None:
    for item in secret_env:
        secret = await db.get(Secret, item.secret_id)
        if secret is None:
            raise DomainError(f"Secret for ${item.name} not found")
        if secret.kind != SecretKind.TEXT:
            raise DomainError(f"${item.name} must use a text secret")


async def list_actions(db: AsyncSession) -> list[Action]:
    return list(await db.scalars(select(Action).order_by(Action.name)))


async def get_action(db: AsyncSession, action_id: uuid.UUID) -> Action:
    action = await db.get(Action, action_id)
    if action is None:
        raise NotFoundError("Action not found")
    return action


async def create_action(db: AsyncSession, body: ActionCreate) -> Action:
    await _check_secrets(db, body.secret_env)
    action = Action(
        name=body.name,
        description=body.description,
        executor=Executor(body.executor),
        target_id=None,
        spec=body.spec.model_dump(mode="json"),
        args=[arg.model_dump(mode="json") for arg in body.args],
        secret_env=[item.model_dump(mode="json") for item in body.secret_env],
        timeout_seconds=body.timeout_seconds,
        concurrency=body.concurrency,
        confirm=body.confirm,
    )
    db.add(action)
    await db.commit()
    return action


async def update_action(db: AsyncSession, action_id: uuid.UUID, body: ActionUpdate) -> Action:
    action = await get_action(db, action_id)
    if body.secret_env is not None:
        await _check_secrets(db, body.secret_env)
        action.secret_env = [item.model_dump(mode="json") for item in body.secret_env]
    if body.args is not None:
        action.args = [arg.model_dump(mode="json") for arg in body.args]
    if body.spec is not None:
        action.spec = body.spec.model_dump(mode="json")
    for name in ("name", "description", "timeout_seconds", "concurrency", "confirm"):
        value = getattr(body, name)
        if value is not None:
            setattr(action, name, value)
    await db.commit()
    return action


async def delete_action(db: AsyncSession, action_id: uuid.UUID) -> None:
    """Delete an Action. Its Runs stay in the history with the action name recorded."""
    await db.delete(await get_action(db, action_id))
    await db.commit()
