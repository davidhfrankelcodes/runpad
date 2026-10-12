"""Feature instances: adding one catalog item (a button or a tile) and keeping what it
generated in sync.

Each instance is one CatalogItem of a Feature, configured: a button instance owns one
Action (an ordinary Action marked with its instance), a tile instance reports one State.
The Action is rebuilt from the Feature's build() whenever the config changes, matched by
its template key, so Buttons and Run history attached to it survive the change.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import pads
from app.errors import DomainError, NotFoundError
from app.features import FEATURES, get_feature
from app.features.base import ActionTemplate, Build, CatalogItem, Feature
from app.models import (
    Action,
    Button,
    FeatureInstance,
    Pad,
    Secret,
    SecretKind,
    State,
    Target,
    Tile,
    User,
)
from app.schemas.actions import check_placeholders
from app.schemas.features import (
    CatalogItemRead,
    FeatureInstanceBatchCreate,
    FeatureInstanceCreate,
    FeatureInstanceRead,
    FeatureInstanceUpdate,
    FeatureRead,
    PadRef,
    StateRead,
    TileTemplateRead,
)


def catalog() -> list[FeatureRead]:
    return [
        FeatureRead(
            id=feature.id,
            name=feature.name,
            description=feature.description,
            icon=feature.icon,
            category=feature.category,
            items=[
                CatalogItemRead(
                    key=item.key, kind=item.kind, name=item.name, description=item.description
                )
                for item in feature.items
            ],
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
    for name in feature.secret_fields():
        secret = await db.get(Secret, getattr(model, name))
        if secret is None:
            raise DomainError(f"{name}: secret not found")
        if secret.kind != SecretKind.TEXT:
            raise DomainError(f"{name}: needs a text secret, not an SSH key")
    return model


def _item(feature: Feature[Any], key: str) -> CatalogItem:
    item = feature.item(key)
    if item is None:
        raise DomainError(f"{feature.name} has no item {key!r}")
    return item


def _build(feature: Feature[Any], config: BaseModel, item: CatalogItem) -> Build:
    result = feature.build_item(config, item.key)
    if not result.actions and not result.tiles:
        raise DomainError(f"{feature.name}: {item.name} is not available with these settings")
    for template in result.actions:
        check_placeholders(template.spec, template.args)  # A bug in the feature if raised.
    return result


def _stored_build(instance: FeatureInstance) -> Build | None:
    """What the instance's stored config builds for its item, or None if the feature is
    gone or its config no longer validates."""
    feature = get_feature(instance.feature_id)
    if feature is None:
        return None
    try:
        return feature.build_item(
            feature.ConfigModel.model_validate(instance.config), instance.item
        )
    except ValidationError:
        return None


def item_kind(instance: FeatureInstance) -> str | None:
    """ "button" or "tile", or None if the feature or item is gone."""
    feature = get_feature(instance.feature_id)
    item = feature.item(instance.item) if feature else None
    return item.kind if item else None


async def to_reads(db: AsyncSession, instances: list[FeatureInstance]) -> list[FeatureInstanceRead]:
    """Instances with what the lists show: their kind, a tile's current State, and the pads
    their button or tile is on."""
    ids = [instance.id for instance in instances]
    states = {
        (state.feature_instance_id, state.key): state
        for state in await db.scalars(select(State).where(State.feature_instance_id.in_(ids)))
    }
    placements: dict[uuid.UUID, dict[uuid.UUID, str]] = {i: {} for i in ids}
    tile_rows = await db.execute(
        select(Tile.feature_instance_id, Pad.id, Pad.name)
        .join(Pad, Tile.pad_id == Pad.id)
        .where(Tile.feature_instance_id.in_(ids))
    )
    button_rows = await db.execute(
        select(Action.feature_instance_id, Pad.id, Pad.name)
        .join(Button, Button.action_id == Action.id)
        .join(Pad, Button.pad_id == Pad.id)
        .where(Action.feature_instance_id.in_(ids))
    )
    for instance_id, pad_id, pad_name in [*tile_rows.all(), *button_rows.all()]:
        if instance_id is not None:
            placements[instance_id][pad_id] = pad_name
    reads = []
    for instance in instances:
        built = _stored_build(instance)
        kind = item_kind(instance)
        state = states.get((instance.id, instance.item)) if kind == "tile" else None
        reads.append(
            FeatureInstanceRead(
                id=instance.id,
                feature_id=instance.feature_id,
                item=instance.item,
                kind=kind,
                name=instance.name,
                config=instance.config,
                tiles=[
                    TileTemplateRead(state_key=t.state_key, label=t.label)
                    for t in (built.tiles if built else [])
                ],
                state=StateRead.model_validate(state) if state else None,
                pads=[
                    PadRef(id=pad_id, name=name)
                    for pad_id, name in sorted(placements[instance.id].items(), key=lambda p: p[1])
                ],
                created_at=instance.created_at,
                updated_at=instance.updated_at,
            )
        )
    return reads


async def to_read(db: AsyncSession, instance: FeatureInstance) -> FeatureInstanceRead:
    [read] = await to_reads(db, [instance])
    return read


def state_keys(instance: FeatureInstance) -> set[str]:
    built = _stored_build(instance)
    return {t.state_key for t in built.tiles} if built else set()


def _apply_template(action: Action, template: ActionTemplate) -> None:
    action.name = template.name
    action.description = template.description
    action.executor = template.executor
    action.target_id = template.target_id
    action.spec = template.spec.model_dump(mode="json")
    action.args = [arg.model_dump(mode="json") for arg in template.args]
    action.secret_env = [item.model_dump(mode="json") for item in template.secret_env]
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
    [instance] = await _create(
        db, user, body.feature_id, [body.item], body.config, body.pad_id, name=body.name
    )
    return instance


async def create_instances(
    db: AsyncSession, user: User, body: FeatureInstanceBatchCreate
) -> list[FeatureInstance]:
    """Add several items of one feature with the same config, all or none."""
    return await _create(db, user, body.feature_id, body.items, body.config, body.pad_id)


async def _create(
    db: AsyncSession,
    user: User,
    feature_id: str,
    item_keys: list[str],
    raw_config: dict[str, Any],
    pad_id: uuid.UUID | None,
    *,
    name: str | None = None,
) -> list[FeatureInstance]:
    """One instance per item. Everything is validated before anything is written, and it is
    committed once, so a refused item adds nothing."""
    feature = _feature(feature_id)
    items = [_item(feature, key) for key in item_keys]
    config = await _validate_config(db, feature, raw_config)
    if pad_id is None and any(item.kind == "tile" for item in items):
        raise DomainError("Choose a pad: a tile only shows on a pad")
    pad = await pads.get_pad(db, user, pad_id) if pad_id else None
    builds = [_build(feature, config, item) for item in items]

    instances = []
    for item, built in zip(items, builds, strict=True):
        # Named after what it adds unless named: "Start plex", or the tile's label.
        generated = built.actions[0].name if built.actions else built.tiles[0].label
        instance = FeatureInstance(
            feature_id=feature.id,
            item=item.key,
            name=(name or generated)[:64],
            config=config.model_dump(mode="json"),
        )
        db.add(instance)
        await db.flush()
        await _place(db, instance, built, pad)
        instances.append(instance)
    await db.commit()
    return instances


async def _place(
    db: AsyncSession, instance: FeatureInstance, built: Build, pad: Pad | None
) -> None:
    """Create the instance's Action, and put its Button or Tile on the pad, after the ones
    already there."""
    actions = []
    for template in built.actions:
        action = Action(feature_instance_id=instance.id, feature_key=template.key)
        _apply_template(action, template)
        db.add(action)
        actions.append(action)
    if pad is None:
        return
    await db.flush()
    position = await pads.next_position(db, pad.id)
    for action, template in zip(actions, built.actions, strict=True):
        if template.button is None:
            continue
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
    for offset, tile in enumerate(built.tiles):
        db.add(
            Tile(
                pad_id=pad.id,
                feature_instance_id=instance.id,
                state_key=tile.state_key,
                label=tile.label,
                position=position + offset,
            )
        )
    await db.flush()


async def update_instance(
    db: AsyncSession, instance_id: uuid.UUID, body: FeatureInstanceUpdate
) -> FeatureInstance:
    instance = await get_instance(db, instance_id)
    if body.name is not None:
        instance.name = body.name
    if body.config is not None:
        feature = _feature(instance.feature_id)
        config = await _validate_config(db, feature, body.config)
        built = _build(feature, config, _item(feature, instance.item))
        await _rebuild(db, instance, built, _stored_build(instance))
        instance.config = config.model_dump(mode="json")
        # States describe the old config; the next poll reports the new one.
        await db.execute(delete(State).where(State.feature_instance_id == instance.id))
    await db.commit()
    return instance


async def _rebuild(
    db: AsyncSession, instance: FeatureInstance, built: Build, previous: Build | None
) -> None:
    """Update Actions in place by key. New templates get an Action without a Button;
    Actions whose template is gone are deleted (their Runs are kept). Tiles for States
    the feature no longer reports are deleted.

    Buttons and Tiles still showing the label generated from the old config get the new
    one; labels the admin changed are left alone.
    """
    old_buttons = {
        t.key: t.button.label for t in (previous.actions if previous else []) if t.button
    }
    existing = {
        action.feature_key: action
        for action in await db.scalars(
            select(Action).where(Action.feature_instance_id == instance.id)
        )
    }
    for template in built.actions:
        action = existing.pop(template.key, None)
        if action is None:
            action = Action(feature_instance_id=instance.id, feature_key=template.key)
            db.add(action)
        elif template.button is not None and template.key in old_buttons:
            await db.execute(
                update(Button)
                .where(Button.action_id == action.id, Button.label == old_buttons[template.key])
                .values(label=template.button.label)
            )
        _apply_template(action, template)
    for action in existing.values():
        await db.delete(action)

    old_tiles = {t.state_key: t.label for t in (previous.tiles if previous else [])}
    keys = {t.state_key for t in built.tiles}
    await db.execute(
        delete(Tile).where(Tile.feature_instance_id == instance.id, Tile.state_key.not_in(keys))
    )
    for tile in built.tiles:
        if tile.state_key in old_tiles:
            await db.execute(
                update(Tile)
                .where(
                    Tile.feature_instance_id == instance.id,
                    Tile.state_key == tile.state_key,
                    Tile.label == old_tiles[tile.state_key],
                )
                .values(label=tile.label)
            )


async def related_tile_instances(db: AsyncSession, instance_id: uuid.UUID) -> list[uuid.UUID]:
    """Tile instances of the same feature with the same config: the tiles a button's Run
    may have changed (pressing "Stop plex" changes the "plex" status tile)."""
    instance = await db.get(FeatureInstance, instance_id)
    if instance is None:
        return []
    siblings = await db.scalars(
        select(FeatureInstance).where(
            FeatureInstance.feature_id == instance.feature_id,
            FeatureInstance.config == instance.config,
        )
    )
    return [s.id for s in siblings if item_kind(s) == "tile"]


async def delete_instance(db: AsyncSession, instance_id: uuid.UUID) -> None:
    """Delete the instance, its Actions, Tiles, and States, and the Actions' Buttons.
    Runs stay in the history."""
    await db.delete(await get_instance(db, instance_id))
    await db.commit()
