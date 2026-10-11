"""Account management: first-run setup, login, and admin user management."""

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AuthenticationError, ConflictError, DomainError, NotFoundError
from app.models import Role, User
from app.security import (
    burn_password_check,
    hash_password,
    password_needs_rehash,
    revoke_user_sessions,
    verify_password,
)

# Serializes first-run setup and changes that could remove the last active admin.
_ADMIN_LOCK_KEY = 0x72756E706164  # "runpad"


async def _lock_admins(db: AsyncSession) -> None:
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _ADMIN_LOCK_KEY})


async def setup_required(db: AsyncSession) -> bool:
    return await db.scalar(select(func.count()).select_from(User)) == 0


async def create_first_admin(db: AsyncSession, username: str, password: str) -> User:
    await _lock_admins(db)
    if not await setup_required(db):
        raise ConflictError("Setup has already been completed")
    user = User(username=username, password_hash=await hash_password(password), role=Role.ADMIN)
    db.add(user)
    await db.commit()
    return user


async def authenticate(db: AsyncSession, username: str, password: str) -> User:
    user = await db.scalar(select(User).where(User.username == username.lower()))
    if user is None or not user.is_active:
        await burn_password_check(password)
        raise AuthenticationError("Invalid username or password")
    if not await verify_password(user.password_hash, password):
        raise AuthenticationError("Invalid username or password")
    if password_needs_rehash(user.password_hash):
        user.password_hash = await hash_password(password)
        await db.commit()
    return user


async def change_own_password(
    db: AsyncSession, user: User, current_password: str, new_password: str, session_token: str
) -> None:
    if not await verify_password(user.password_hash, current_password):
        raise DomainError("Current password is incorrect")
    user.password_hash = await hash_password(new_password)
    await revoke_user_sessions(db, user.id, keep_token=session_token)
    await db.commit()


async def list_users(db: AsyncSession) -> list[User]:
    return list(await db.scalars(select(User).order_by(User.username)))


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


async def create_user(db: AsyncSession, username: str, password: str, role: Role) -> User:
    user = User(username=username, password_hash=await hash_password(password), role=role)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Username is already taken") from exc
    return user


async def update_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    role: Role | None = None,
    is_active: bool | None = None,
    password: str | None = None,
    session_token: str,
) -> User:
    await _lock_admins(db)
    user = await get_user(db, user_id)

    loses_admin = (
        user.role == Role.ADMIN and user.is_active and (role == Role.MEMBER or is_active is False)
    )
    if loses_admin:
        active_admins = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.ADMIN, User.is_active.is_(True))
        )
        if active_admins == 1:
            raise ConflictError("At least one active admin is required")

    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active
        if not is_active:
            await revoke_user_sessions(db, user.id)
    if password is not None:
        user.password_hash = await hash_password(password)
        await revoke_user_sessions(db, user.id, keep_token=session_token)
    await db.commit()
    return user
