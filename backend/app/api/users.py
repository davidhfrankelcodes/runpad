import uuid

from fastapi import APIRouter, status

from app import users
from app.api.deps import AdminUser, DbSession, SessionToken
from app.schemas.users import UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
async def list_users(_: AdminUser, db: DbSession) -> list[UserRead]:
    return [UserRead.model_validate(u) for u in await users.list_users(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, _: AdminUser, db: DbSession) -> UserRead:
    user = await users.create_user(db, body.username, body.password, body.role)
    return UserRead.model_validate(user)


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: UserUpdate, _: AdminUser, token: SessionToken, db: DbSession
) -> UserRead:
    """Change role, (de)activate, or reset the password. Deactivating logs the user out."""
    user = await users.update_user(
        db,
        user_id,
        role=body.role,
        is_active=body.is_active,
        password=body.password,
        session_token=token,
    )
    return UserRead.model_validate(user)
