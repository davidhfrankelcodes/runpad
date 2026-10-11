"""Passwords, sessions, and request-level protections."""

import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserSession

SESSION_COOKIE = "runpad_session"
SESSION_LIFETIME = timedelta(days=30)
# Sliding expiry is written back at most this often, not on every request.
SESSION_REFRESH_INTERVAL = timedelta(days=1)

# Unsafe API requests must carry this header. Cross-site pages cannot set custom
# headers without a CORS preflight, which runpad never grants.
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "runpad"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_hasher = PasswordHasher()
# Verified against when a username does not exist, so response time does not reveal it.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def utcnow() -> datetime:
    return datetime.now(UTC)


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    try:
        return await asyncio.to_thread(_hasher.verify, password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


async def burn_password_check(password: str) -> None:
    await verify_password(_DUMMY_HASH, password)


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(db: AsyncSession, user: User) -> str:
    """Create a session for the user and return the raw cookie token."""
    now = utcnow()
    await db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id, token_hash=hash_token(token), expires_at=now + SESSION_LIFETIME
        )
    )
    await db.commit()
    return token


async def resolve_session(db: AsyncSession, token: str) -> tuple[User, bool] | None:
    """Return the session's user and whether the expiry was extended, or None if invalid."""
    now = utcnow()
    session = await db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token), UserSession.expires_at > now
        )
    )
    if session is None or not session.user.is_active:
        return None
    refreshed = session.expires_at - now < SESSION_LIFETIME - SESSION_REFRESH_INTERVAL
    if refreshed:
        session.expires_at = now + SESSION_LIFETIME
        await db.commit()
    return session.user, refreshed


async def delete_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
    await db.commit()


async def revoke_user_sessions(
    db: AsyncSession, user_id: uuid.UUID, keep_token: str | None = None
) -> None:
    """Delete all of a user's sessions, optionally keeping the caller's current one."""
    stmt = delete(UserSession).where(UserSession.user_id == user_id)
    if keep_token is not None:
        stmt = stmt.where(UserSession.token_hash != hash_token(keep_token))
    await db.execute(stmt)


def csrf_header_ok(method: str, path: str, headers: dict[str, str]) -> bool:
    if method in SAFE_METHODS or not path.startswith("/api/"):
        return True
    return headers.get(CSRF_HEADER.lower()) == CSRF_HEADER_VALUE
