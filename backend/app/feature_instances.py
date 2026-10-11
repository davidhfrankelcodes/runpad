"""Feature instances: enabling a catalog Feature, and keeping its generated Actions in sync.

Generated Actions are ordinary Actions marked with their instance. They are rebuilt from
the Feature's build() whenever the config changes, matched by their template key, so
Buttons and Run history attached to them survive the change.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import pads
from app.errors import DomainError, NotFoundError
from app.features import FEATURES, get_feature
from app.features.base import ActionTemplate, Feature
from app.models import Action, Button, FeatureInstance, Target, User
from app.schemas.actions import check_placeholders
from app.schemas.features import FeatureInstanceCreate, FeatureInstanceUpdate, FeatureRead


def catalog() -> list[FeatureRead]:
    return [
        FeatureRead(
            id=feature.id,
            name=feature.name,
            description=feature.description,
            icon=feature.icon,
            category=feature.category,
            config_schema=feature.config_schema(),
        )
        for feature in FEATURES.values()
    ]


def _feature(feature_id: str) -> Feature[Any]:
    feature = get_feature(feature_id)
    if feature is None:
        raise DomainError(f"Unknown feature: {feature_id}")
    return feature


def _validation_message(exc: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(part) for part in error['loc']) or 'config'}: {error['msg']}"
        for error in exc.errors()
    )


async def _validate_config(
    db: AsyncSession, feature: Feature[Any], config: dict[str, Any]
) -> BaseModel:
    try:
        model = feature.ConfigModel.model_validate(config)
    except ValidationError as exc:
        raise DomainError(_validation_message(exc)) from exc
    for name, kind in feature.target_fields().items():
        target = await db.get(Target, getattr(model, name))
        if target is None:
            raise DomainError(f"{name}: target not found")
        if target.kind != kind:
            raise DomainError(f"{name}: needs a {kind.value} target")
    return model


def _build(feature: Feature[Any], config: BaseModel) -> list[ActionTemplate]:
    templates = feature.build(config)
    for template in templates:
        check_placeholders(template.spec, template.args)  # A bug in the feature if raised.
    return templates


def _apply_template(action: Action, template: ActionTemplate) -> None:
    action.name = template.name
    action.description = template.description
    action.executor = template.executor
    action.target_id = template.target_id
    action.spec = template.spec.model_dump(mode="json")
    action.args = [arg.model_dump(mode="json") for arg in template.args]
    action.secret_env = []
    action.timeout_seconds = template.timeout_seconds
    action.concurrency = template.concurrency
    action.confirm = template.confirm


async def list_instances(db: AsyncSession) -> list[FeatureInstance]:
    return list(
        await db.scalars(
            select(FeatureInstance).order_by(FeatureInstance.name, FeatureInstance.created_at)
        )
    )


async def get_instance(db: AsyncSession, instance_id: uuid.UUID) -> FeatureInstance:
    instance = await db.get(FeatureInstance, instance_id)
    if instance is None:
        raise NotFoundError("Feature instance not found")
    return instance


async def create_instance(
    db: AsyncSession, user: User, body: FeatureInstanceCreate
) -> FeatureInstance:
    feature = _feature(body.feature_id)
    config = await _validate_config(db, feature, body.config)
    pad = await pads.get_pad(db, user, body.pad_id) if body.pad_id else None
    templates = _build(feature, config)

    instance = FeatureInstance(
        feature_id=feature.id, name=body.name, config=config.model_dump(mode="json")
    )
    db.add(instance)
    await db.flush()
    position = 0
    if pad is not None:
        position = await db.scalar(
            select(func.coalesce(func.max(Button.position) + 1, 0)).where(Button.pad_id == pad.id)
        )
    for template in templates:
        action = Action(feature_instance_id=instance.id, feature_key=template.key)
        _apply_template(action, template)
        db.add(action)
        if pad is not None and template.button is not None:
            await db.flush()
            db.add(
                Button(
                    pad_id=pad.id,
                    action_id=action.id,
                    label=template.button.label,
                    color=template.button.color,
                    position=position,
                )
            )
            position += 1
    await db.commit()
    return instance


async def update_instance(
    db: AsyncSession, instance_id: uuid.UUID, body: FeatureInstanceUpdate
) -> FeatureInstance:
    instance = await get_instance(db, instance_id)
    if body.name is not None:
        instance.name = body.name
    if body.config is not None:
        feature = _feature(instance.feature_id)
        config = await _validate_config(db, feature, body.config)
        previous = _previous_labels(feature, instance.config)
        await _rebuild(db, instance, _build(feature, config), previous)
        instance.config = config.model_dump(mode="json")
    await db.commit()
    return instance


def _previous_labels(feature: Feature[Any], config: dict[str, Any]) -> dict[str, str]:
    """The button labels the current config generated, by template key."""
    try:
        templates = feature.build(feature.ConfigModel.model_validate(config))
    except ValidationError:  # Stored by an older version of the feature.
        return {}
    return {t.key: t.button.label for t in templates if t.button is not None}


async def _rebuild(
    db: AsyncSession,
    instance: FeatureInstance,
    templates: list[ActionTemplate],
    previous_labels: dict[str, str],
) -> None:
    """Update Actions in place by key. New templates get an Action without a Button;
    Actions whose template is gone are deleted (their Runs are kept).

    Buttons still showing the label generated from the old config get the new one;
    labels the admin changed are left alone.
    """
    existing = {
        action.feature_key: action
        for action in await db.scalars(
            select(Action).where(Action.feature_instance_id == instance.id)
        )
    }
    for template in templates:
        action = existing.pop(template.key, None)
        if action is None:
            action = Action(feature_instance_id=instance.id, feature_key=template.key)
            db.add(action)
        else:
            old_label = previous_labels.get(template.key)
            if template.button is not None and old_label is not None:
                await db.execute(
                    update(Button)
                    .where(Button.action_id == action.id, Button.label == old_label)
                    .values(label=template.button.label)
                )
        _apply_template(action, template)
    for action in existing.values():
        await db.delete(action)


async def delete_instance(db: AsyncSession, instance_id: uuid.UUID) -> None:
    """Delete the instance, its Actions, and their Buttons. Runs stay in the history."""
    await db.delete(await get_instance(db, instance_id))
    await db.commit()
