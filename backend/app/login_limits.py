"""Rate limiting for password guessing, stored in Postgres.

Failed logins are counted per client IP and per username over a sliding window. The
per-username limit is higher, so one attacker cannot easily lock a user out, while
guessing spread across many IPs is still capped. Behind a reverse proxy, the client IP
comes from X-Forwarded-For only if uvicorn trusts the proxy (RUNPAD_TRUSTED_PROXIES).
"""

import logging
import math
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import TooManyRequestsError
from app.models import LoginFailure
from app.security import utcnow

logger = logging.getLogger(__name__)

WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_IP = 10
MAX_FAILURES_PER_USERNAME = 50


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _username(username: str) -> str:
    return username.lower()[:32]


async def _retry_after(
    db: AsyncSession, condition: ColumnElement[bool], limit: int, now: datetime
) -> int | None:
    """Seconds until fewer than `limit` failures match, or None if already below it."""
    recent = select(LoginFailure.created_at).where(
        condition, LoginFailure.created_at > now - WINDOW
    )
    count = await db.scalar(select(func.count()).select_from(recent.subquery()))
    if not count or count < limit:
        return None
    # The failure that has to expire for the count to drop below the limit.
    oldest_blocking = await db.scalar(
        recent.order_by(LoginFailure.created_at.desc()).offset(limit - 1).limit(1)
    )
    if oldest_blocking is None:
        return None
    return max(1, math.ceil((oldest_blocking + WINDOW - now).total_seconds()))


async def check(db: AsyncSession, ip: str, username: str) -> None:
    """Refuse to check a password while this IP or username has too many failures."""
    now = utcnow()
    waits = [
        await _retry_after(db, LoginFailure.ip == ip, MAX_FAILURES_PER_IP, now),
        await _retry_after(
            db, LoginFailure.username == _username(username), MAX_FAILURES_PER_USERNAME, now
        ),
    ]
    if wait := max((w for w in waits if w is not None), default=None):
        minutes = math.ceil(wait / 60)
        raise TooManyRequestsError(
            f"Too many failed logins. Try again in {minutes} minute{'s' if minutes > 1 else ''}.",
            retry_after_seconds=wait,
        )


async def record_failure(db: AsyncSession, ip: str, username: str) -> None:
    # Logged for tools like fail2ban.
    logger.warning("Failed login for user %r from %s", _username(username), ip)
    now = utcnow()
    await db.execute(delete(LoginFailure).where(LoginFailure.created_at <= now - WINDOW))
    db.add(LoginFailure(username=_username(username), ip=ip, created_at=now, updated_at=now))
    await db.commit()


async def clear(db: AsyncSession, ip: str, username: str) -> None:
    """After a successful login, forget this IP's failures for this username."""
    await db.execute(
        delete(LoginFailure).where(
            LoginFailure.ip == ip, LoginFailure.username == _username(username)
        )
    )
    await db.commit()
