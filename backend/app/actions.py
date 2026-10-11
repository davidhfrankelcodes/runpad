"""Actions: stored commands with typed arguments. Runs are started through runner.py."""

import uuid

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, DomainError, NotFoundError
from app.models import Action, Executor, Secret, SecretKind, Target, TargetKind
from app.schemas.actions import (
    ActionCreate,
    ActionUpdate,
    ArgSpec,
    HttpSpec,
    ScriptSpec,
    SecretEnv,
    check_placeholders,
)

_TARGET_KIND = {Executor.SSH: TargetKind.SSH, Executor.HTTP: TargetKind.HTTP}
_SPEC_MODEL: dict[Executor, type[ScriptSpec] | type[HttpSpec]] = {
    Executor.LOCAL: ScriptSpec,
    Executor.SSH: ScriptSpec,
    Executor.HTTP: HttpSpec,
}
_arg_specs = TypeAdapter(list[ArgSpec])


async def _check_secrets(db: AsyncSession, secret_env: list[SecretEnv]) -> None:
    for item in secret_env:
        secret = await db.get(Secret, item.secret_id)
        if secret is None:
            raise DomainError(f"Secret for ${item.name} not found")
        if secret.kind != SecretKind.TEXT:
            raise DomainError(f"${item.name} must use a text secret")


async def _check_target(db: AsyncSession, executor: Executor, target_id: uuid.UUID) -> None:
    target = await db.get(Target, target_id)
    if target is None:
        raise DomainError("Target not found")
    expected = _TARGET_KIND[executor]
    if target.kind != expected:
        raise DomainError(f"A {executor.value} action needs a {expected.value} target")


async def list_actions(db: AsyncSession) -> list[Action]:
    return list(await db.scalars(select(Action).order_by(Action.name)))


async def get_action(db: AsyncSession, action_id: uuid.UUID) -> Action:
    action = await db.get(Action, action_id)
    if action is None:
        raise NotFoundError("Action not found")
    return action


def _check_unmanaged(action: Action) -> None:
    if action.feature_instance_id is not None:
        raise ConflictError(
            f"{action.name} is managed by a feature. Change or delete it on the Features page."
        )


async def create_action(db: AsyncSession, body: ActionCreate) -> Action:
    executor = Executor(body.executor)
    target_id = getattr(body, "target_id", None)
    if target_id is not None:
        await _check_target(db, executor, target_id)
    await _check_secrets(db, body.secret_env)
    action = Action(
        name=body.name,
        description=body.description,
        executor=executor,
        target_id=target_id,
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
    _check_unmanaged(action)
    if body.target_id is not None:
        if action.executor == Executor.LOCAL:
            raise DomainError("Local actions have no target")
        await _check_target(db, action.executor, body.target_id)
        action.target_id = body.target_id
    if body.secret_env is not None:
        if body.secret_env and action.executor == Executor.HTTP:
            raise DomainError("HTTP actions cannot use secret variables")
        await _check_secrets(db, body.secret_env)
        action.secret_env = [item.model_dump(mode="json") for item in body.secret_env]
    if body.spec is not None:
        if not isinstance(body.spec, _SPEC_MODEL[action.executor]):
            raise DomainError(f"Spec does not match a {action.executor.value} action")
        action.spec = body.spec.model_dump(mode="json")
    if body.args is not None:
        action.args = [arg.model_dump(mode="json") for arg in body.args]
    for name in ("name", "description", "timeout_seconds", "concurrency", "confirm"):
        value = getattr(body, name)
        if value is not None:
            setattr(action, name, value)
    try:
        check_placeholders(
            _SPEC_MODEL[action.executor].model_validate(action.spec),
            _arg_specs.validate_python(action.args),
        )
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    await db.commit()
    return action


async def delete_action(db: AsyncSession, action_id: uuid.UUID) -> None:
    """Delete an Action. Its Runs stay in the history with the action name recorded."""
    action = await get_action(db, action_id)
    _check_unmanaged(action)
    await db.delete(action)
    await db.commit()
