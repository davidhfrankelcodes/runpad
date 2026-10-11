"""Pads and buttons, and who may see and press them."""

import uuid

from sqlalchemy import Select, any_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import DomainError, NotFoundError, PermissionDeniedError
from app.models import Action, Button, Pad, Role, User
from app.schemas.pads import (
    ButtonAction,
    ButtonCreate,
    ButtonRead,
    ButtonUpdate,
    PadCreate,
    PadDetail,
    PadRead,
    PadUpdate,
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
        select(Button, Action)
        .join(Action, Button.action_id == Action.id)
        .where(Button.pad_id == pad.id)
        .order_by(Button.position, Button.created_at)
    )
    buttons = [_button_read(button, action) for button, action in rows.all()]
    return PadDetail(**to_read(pad, user).model_dump(), buttons=buttons)


def _button_read(button: Button, action: Action) -> ButtonRead:
    return ButtonRead(
        id=button.id,
        pad_id=button.pad_id,
        label=button.label,
        color=button.color,
        position=button.position,
        action=ButtonAction.model_validate(action),
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


async def _reorder(db: AsyncSession, items: list[Pad] | list[Button], ids: list[uuid.UUID]) -> None:
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
    position = await db.scalar(
        select(func.coalesce(func.max(Button.position) + 1, 0)).where(Button.pad_id == pad.id)
    )
    button = Button(
        pad_id=pad.id, action_id=action.id, label=body.label, color=body.color, position=position
    )
    db.add(button)
    await db.commit()
    return _button_read(button, action)


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
        button.position = await db.scalar(
            select(func.coalesce(func.max(Button.position) + 1, 0)).where(Button.pad_id == pad.id)
        )
    if body.label is not None:
        button.label = body.label
    if body.color is not None:
        button.color = body.color
    await db.commit()
    action = await db.get(Action, button.action_id)
    if action is None:  # Deleted concurrently; its buttons go with it.
        raise NotFoundError("Button not found")
    return _button_read(button, action)


async def delete_button(db: AsyncSession, button_id: uuid.UUID) -> None:
    await db.delete(await _get_button(db, button_id))
    await db.commit()


async def reorder_buttons(
    db: AsyncSession, user: User, pad_id: uuid.UUID, ids: list[uuid.UUID]
) -> None:
    pad = await get_pad(db, user, pad_id)
    buttons = list(await db.scalars(select(Button).where(Button.pad_id == pad.id)))
    await _reorder(db, buttons, ids)


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
