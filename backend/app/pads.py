"""Pads and buttons, and who may see and press them."""

import uuid

from sqlalchemy import Select, any_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import DomainError, NotFoundError, PermissionDeniedError
from app.features import get_feature
from app.models import (
    Action,
    Button,
    Executor,
    FeatureInstance,
    Pad,
    Role,
    State,
    Tile,
    User,
)
from app.schemas.features import StateRead
from app.schemas.pads import (
    ButtonAction,
    ButtonCreate,
    ButtonRead,
    ButtonUpdate,
    ItemKind,
    PadCreate,
    PadDetail,
    PadRead,
    PadUpdate,
    TileCreate,
    TileRead,
    TileUpdate,
)


def _visible(user: User) -> Select[tuple[Pad]]:
    query = select(Pad)
    if user.role != Role.ADMIN:
        query = query.where(any_(Pad.member_ids) == user.id)
    return query


def to_read(pad: Pad, user: User) -> PadRead:
    # Members do not learn who else can see a pad.
    member_ids = pad.member_ids if user.role == Role.ADMIN else []
    return PadRead(id=pad.id, name=pad.name, position=pad.position, member_ids=member_ids)


async def _check_members(db: AsyncSession, member_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    unique = list(dict.fromkeys(member_ids))
    found = set(await db.scalars(select(User.id).where(User.id.in_(unique))))
    if missing := [str(i) for i in unique if i not in found]:
        raise DomainError(f"Unknown users: {', '.join(missing)}")
    return unique


async def list_pads(db: AsyncSession, user: User) -> list[Pad]:
    return list(await db.scalars(_visible(user).order_by(Pad.position, Pad.name)))


async def get_pad(db: AsyncSession, user: User, pad_id: uuid.UUID) -> Pad:
    pad = await db.scalar(_visible(user).where(Pad.id == pad_id))
    if pad is None:
        raise NotFoundError("Pad not found")
    return pad


async def pad_detail(db: AsyncSession, user: User, pad_id: uuid.UUID) -> PadDetail:
    pad = await get_pad(db, user, pad_id)
    rows = await db.execute(
        select(Button, Action, FeatureInstance.feature_id)
        .join(Action, Button.action_id == Action.id)
        .outerjoin(FeatureInstance, Action.feature_instance_id == FeatureInstance.id)
        .where(Button.pad_id == pad.id)
        .order_by(Button.position, Button.created_at)
    )
    buttons = [_button_read(button, action, feature_id) for button, action, feature_id in rows]
    tile_rows = await db.execute(
        select(Tile, State, FeatureInstance.feature_id)
        .join(FeatureInstance, Tile.feature_instance_id == FeatureInstance.id)
        .outerjoin(
            State,
            (State.feature_instance_id == Tile.feature_instance_id) & (State.key == Tile.state_key),
        )
        .where(Tile.pad_id == pad.id)
        .order_by(Tile.position, Tile.created_at)
    )
    tiles = [_tile_read(tile, state, feature_id) for tile, state, feature_id in tile_rows]
    return PadDetail(**to_read(pad, user).model_dump(), buttons=buttons, tiles=tiles)


def _feature_kind(feature_id: str) -> ItemKind:
    feature = get_feature(feature_id)
    if feature is None:  # Removed from the catalog in a later version.
        return ItemKind(name=feature_id, icon="feature")
    return ItemKind(name=feature.name, icon=feature.icon)


def _action_kind(action: Action, feature_id: str | None) -> ItemKind:
    if feature_id is not None:
        return _feature_kind(feature_id)
    if action.executor == Executor.HTTP:
        return ItemKind(name="Custom request", icon="webhook")
    return ItemKind(name="Custom command", icon="terminal")


async def _feature_id_of(db: AsyncSession, action: Action) -> str | None:
    if action.feature_instance_id is None:
        return None
    return await db.scalar(
        select(FeatureInstance.feature_id).where(FeatureInstance.id == action.feature_instance_id)
    )


def _check_interval(feature_id: str) -> int | None:
    feature = get_feature(feature_id)
    return feature.poll.interval_seconds if feature and feature.poll else None


def _tile_read(tile: Tile, state: State | None, feature_id: str) -> TileRead:
    return TileRead(
        id=tile.id,
        pad_id=tile.pad_id,
        feature_instance_id=tile.feature_instance_id,
        state_key=tile.state_key,
        label=tile.label,
        position=tile.position,
        kind=_feature_kind(feature_id),
        check_interval_seconds=_check_interval(feature_id),
        state=StateRead.model_validate(state) if state else None,
    )


def _button_read(button: Button, action: Action, feature_id: str | None) -> ButtonRead:
    return ButtonRead(
        id=button.id,
        pad_id=button.pad_id,
        label=button.label,
        color=button.color,
        position=button.position,
        action=ButtonAction(
            id=action.id,
            name=action.name,
            description=action.description,
            args=action.args,
            confirm=action.confirm,
            kind=_action_kind(action, feature_id),
        ),
    )


async def create_pad(db: AsyncSession, body: PadCreate) -> Pad:
    position = await db.scalar(select(func.coalesce(func.max(Pad.position) + 1, 0)))
    pad = Pad(
        name=body.name,
        member_ids=await _check_members(db, body.member_ids),
        position=position,
    )
    db.add(pad)
    await db.commit()
    return pad


async def update_pad(db: AsyncSession, user: User, pad_id: uuid.UUID, body: PadUpdate) -> Pad:
    pad = await get_pad(db, user, pad_id)
    if body.name is not None:
        pad.name = body.name
    if body.member_ids is not None:
        pad.member_ids = await _check_members(db, body.member_ids)
    await db.commit()
    return pad


async def delete_pad(db: AsyncSession, user: User, pad_id: uuid.UUID) -> None:
    """Delete a pad and its buttons. The Actions behind the buttons are kept."""
    await db.delete(await get_pad(db, user, pad_id))
    await db.commit()


async def _reorder(
    db: AsyncSession, items: list[Pad] | list[Button] | list[Tile], ids: list[uuid.UUID]
) -> None:
    by_id = {item.id: item for item in items}
    if sorted(by_id) != sorted(ids):
        raise DomainError("The order must list every item exactly once")
    for position, item_id in enumerate(ids):
        by_id[item_id].position = position
    await db.commit()


async def reorder_pads(db: AsyncSession, user: User, ids: list[uuid.UUID]) -> None:
    await _reorder(db, await list_pads(db, user), ids)


async def create_button(
    db: AsyncSession, user: User, pad_id: uuid.UUID, body: ButtonCreate
) -> ButtonRead:
    pad = await get_pad(db, user, pad_id)
    action = await db.get(Action, body.action_id)
    if action is None:
        raise DomainError("Action not found")
    button = Button(
        pad_id=pad.id,
        action_id=action.id,
        label=body.label,
        color=body.color,
        position=await next_position(db, Button, pad.id),
    )
    db.add(button)
    await db.commit()
    return _button_read(button, action, await _feature_id_of(db, action))


async def _get_button(db: AsyncSession, button_id: uuid.UUID) -> Button:
    button = await db.get(Button, button_id)
    if button is None:
        raise NotFoundError("Button not found")
    return button


async def update_button(
    db: AsyncSession, user: User, button_id: uuid.UUID, body: ButtonUpdate
) -> ButtonRead:
    button = await _get_button(db, button_id)
    if body.pad_id is not None and body.pad_id != button.pad_id:
        pad = await get_pad(db, user, body.pad_id)
        button.pad_id = pad.id
        button.position = await next_position(db, Button, pad.id)
    if body.label is not None:
        button.label = body.label
    if body.color is not None:
        button.color = body.color
    await db.commit()
    action = await db.get(Action, button.action_id)
    if action is None:  # Deleted concurrently; its buttons go with it.
        raise NotFoundError("Button not found")
    return _button_read(button, action, await _feature_id_of(db, action))


async def delete_button(db: AsyncSession, button_id: uuid.UUID) -> None:
    await db.delete(await _get_button(db, button_id))
    await db.commit()


async def reorder_buttons(
    db: AsyncSession, user: User, pad_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    pad = await get_pad(db, user, pad_id)
    buttons = list(await db.scalars(select(Button).where(Button.pad_id == pad.id)))
    await _reorder(db, buttons, ids)


async def next_position(
    db: AsyncSession, model: type[Button] | type[Tile], pad_id: uuid.UUID
) -> int:
    position = await db.scalar(
        select(func.coalesce(func.max(model.position) + 1, 0)).where(model.pad_id == pad_id)
    )
    return int(position or 0)


async def create_tile(
    db: AsyncSession, user: User, pad_id: uuid.UUID, body: TileCreate, state_keys: set[str]
) -> TileRead:
    """Add a tile for one of an instance's States. `state_keys` are those it reports."""
    pad = await get_pad(db, user, pad_id)
    if await db.get(FeatureInstance, body.feature_instance_id) is None:
        raise DomainError("Feature instance not found")
    if body.state_key not in state_keys:
        raise DomainError(f"This feature has no state {body.state_key!r}")
    tile = Tile(
        pad_id=pad.id,
        feature_instance_id=body.feature_instance_id,
        state_key=body.state_key,
        label=body.label,
        position=await next_position(db, Tile, pad.id),
    )
    db.add(tile)
    await db.commit()
    return await _load_tile(db, tile)


async def _get_tile(db: AsyncSession, tile_id: uuid.UUID) -> Tile:
    tile = await db.get(Tile, tile_id)
    if tile is None:
        raise NotFoundError("Tile not found")
    return tile


async def _load_tile(db: AsyncSession, tile: Tile) -> TileRead:
    state = await db.scalar(
        select(State).where(
            State.feature_instance_id == tile.feature_instance_id, State.key == tile.state_key
        )
    )
    feature_id = await db.scalar(
        select(FeatureInstance.feature_id).where(FeatureInstance.id == tile.feature_instance_id)
    )
    return _tile_read(tile, state, feature_id or "")


async def update_tile(
    db: AsyncSession, user: User, tile_id: uuid.UUID, body: TileUpdate
) -> TileRead:
    tile = await _get_tile(db, tile_id)
    if body.pad_id is not None and body.pad_id != tile.pad_id:
        pad = await get_pad(db, user, body.pad_id)
        tile.pad_id = pad.id
        tile.position = await next_position(db, Tile, pad.id)
    if body.label is not None:
        tile.label = body.label
    await db.commit()
    return await _load_tile(db, tile)


async def delete_tile(db: AsyncSession, tile_id: uuid.UUID) -> None:
    await db.delete(await _get_tile(db, tile_id))
    await db.commit()


async def reorder_tiles(
    db: AsyncSession, user: User, pad_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    pad = await get_pad(db, user, pad_id)
    tiles = list(await db.scalars(select(Tile).where(Tile.pad_id == pad.id)))
    await _reorder(db, tiles, ids)


async def can_see_instance(db: AsyncSession, user: User, instance_id: uuid.UUID) -> bool:
    """Whether a user sees any tile of a Feature instance (for State events)."""
    if user.role == Role.ADMIN:
        return True
    return bool(
        await db.scalar(
            select(
                exists()
                .where(Tile.feature_instance_id == instance_id)
                .where(Tile.pad_id == Pad.id)
                .where(any_(Pad.member_ids) == user.id)
            )
        )
    )


async def check_can_run(db: AsyncSession, user: User, action_id: uuid.UUID) -> None:
    """Admins can run anything. Members can run an Action behind a button on a pad they see."""
    if user.role == Role.ADMIN:
        return
    on_visible_pad = await db.scalar(
        select(
            exists()
            .where(Button.action_id == action_id)
            .where(Button.pad_id == Pad.id)
            .where(any_(Pad.member_ids) == user.id)
        )
    )
    if not on_visible_pad:
        raise PermissionDeniedError("You cannot run this action")
