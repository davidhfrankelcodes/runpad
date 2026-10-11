"""Personal API tokens: created by a user for scripts and tools, sent as a bearer token.

A token acts as its user, with the user's role, until it expires, is revoked, or the user is
deactivated. Only a SHA-256 hash is stored, as for session cookies.
"""

import secrets
import uuid
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models import ApiToken, User
from app.schemas.api_tokens import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from app.security import hash_token, utcnow

TOKEN_PREFIX = "rp_"  # noqa: S105 - a fixed marker, not a credential
# last_used_at is written back at most this often, not on every request.
LAST_USED_INTERVAL = timedelta(minutes=1)


async def list_tokens(db: AsyncSession, user: User) -> list[ApiTokenRead]:
    tokens = await db.scalars(
        select(ApiToken).where(ApiToken.user_id == user.id).order_by(ApiToken.created_at.desc())
    )
    return [ApiTokenRead.model_validate(token) for token in tokens]


async def create_token(db: AsyncSession, user: User, body: ApiTokenCreate) -> ApiTokenCreated:
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user.id,
        name=body.name,
        token_hash=hash_token(raw),
        prefix=raw[: len(TOKEN_PREFIX) + 6],
        expires_at=(
            utcnow() + timedelta(days=body.expires_in_days) if body.expires_in_days else None
        ),
    )
    db.add(token)
    await db.commit()
    return ApiTokenCreated(**ApiTokenRead.model_validate(token).model_dump(), token=raw)


async def revoke_token(db: AsyncSession, user: User, token_id: uuid.UUID) -> None:
    result = await db.execute(
        delete(ApiToken).where(ApiToken.id == token_id, ApiToken.user_id == user.id)
    )
    if result.rowcount == 0:  # type: ignore[attr-defined]
        raise NotFoundError("Token not found")
    await db.commit()


async def resolve_token(db: AsyncSession, raw: str) -> User | None:
    """The token's user, or None if the token is unknown, expired, or its user inactive."""
    now = utcnow()
    token = await db.scalar(select(ApiToken).where(ApiToken.token_hash == hash_token(raw)))
    if token is None or not token.user.is_active:
        return None
    if token.expires_at is not None and token.expires_at <= now:
        return None
    if token.last_used_at is None or now - token.last_used_at >= LAST_USED_INTERVAL:
        token.last_used_at = now
        await db.commit()
    return token.user
