import uuid

from fastapi import APIRouter, status

from app import pads
from app.api.deps import AdminUser, CurrentUser, DbSession
from app.schemas.pads import (
    ButtonCreate,
    ButtonRead,
    ButtonUpdate,
    Order,
    PadCreate,
    PadDetail,
    PadRead,
    PadUpdate,
)

router = APIRouter(tags=["pads"])


@router.get("/pads")
async def list_pads(user: CurrentUser, db: DbSession) -> list[PadRead]:
    """Pads you can see: all of them for admins, those listing you for members."""
    return [pads.to_read(pad, user) for pad in await pads.list_pads(db, user)]


@router.post("/pads", status_code=status.HTTP_201_CREATED)
async def create_pad(body: PadCreate, user: AdminUser, db: DbSession) -> PadRead:
    return pads.to_read(await pads.create_pad(db, body), user)


@router.put("/pads/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_pads(body: Order, user: AdminUser, db: DbSession) -> None:
    await pads.reorder_pads(db, user, body.ids)


@router.get("/pads/{pad_id}")
async def get_pad(pad_id: uuid.UUID, user: CurrentUser, db: DbSession) -> PadDetail:
    return await pads.pad_detail(db, user, pad_id)


@router.patch("/pads/{pad_id}")
async def update_pad(pad_id: uuid.UUID, body: PadUpdate, user: AdminUser, db: DbSession) -> PadRead:
    return pads.to_read(await pads.update_pad(db, user, pad_id, body), user)


@router.delete("/pads/{pad_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pad(pad_id: uuid.UUID, user: AdminUser, db: DbSession) -> None:
    """Delete a pad and its buttons. The Actions are kept."""
    await pads.delete_pad(db, user, pad_id)


@router.post("/pads/{pad_id}/buttons", status_code=status.HTTP_201_CREATED)
async def create_button(
    pad_id: uuid.UUID, body: ButtonCreate, user: AdminUser, db: DbSession
) -> ButtonRead:
    return await pads.create_button(db, user, pad_id, body)


@router.put("/pads/{pad_id}/buttons/order", status_code=status.HTTP_204_NO_CONTENT)
async def reorder_buttons(pad_id: uuid.UUID, body: Order, user: AdminUser, db: DbSession) -> None:
    await pads.reorder_buttons(db, user, pad_id, body.ids)


@router.patch("/buttons/{button_id}")
async def update_button(
    button_id: uuid.UUID, body: ButtonUpdate, user: AdminUser, db: DbSession
) -> ButtonRead:
    return await pads.update_button(db, user, button_id, body)


@router.delete("/buttons/{button_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_button(button_id: uuid.UUID, _: AdminUser, db: DbSession) -> None:
    await pads.delete_button(db, button_id)
