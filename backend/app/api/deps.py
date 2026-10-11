from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import AuthenticationError, PermissionDeniedError
from app.models import Role, User
from app.security import SESSION_COOKIE, SESSION_LIFETIME, SecretCipher, resolve_session

DbSession = Annotated[AsyncSession, Depends(get_session)]


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


def session_token(request: Request) -> str:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthenticationError("Not logged in")
    return token


SessionToken = Annotated[str, Depends(session_token)]


async def current_user(
    request: Request, response: Response, db: DbSession, token: SessionToken
) -> User:
    resolved = await resolve_session(db, token)
    if resolved is None:
        raise AuthenticationError("Not logged in")
    user, refreshed = resolved
    if refreshed:
        set_session_cookie(request, response, token)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise PermissionDeniedError("Admin role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def secret_cipher(request: Request) -> SecretCipher:
    return request.app.state.cipher


Cipher = Annotated[SecretCipher, Depends(secret_cipher)]
