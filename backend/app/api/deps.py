from typing import Annotated

from fastapi import Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app import api_tokens
from app.db import get_session
from app.errors import AuthenticationError, PermissionDeniedError
from app.events import EventBus
from app.models import Role, User
from app.poller import Poller
from app.runner import Runner
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


def _authorization(request: Request) -> str | None:
    return request.headers.get("authorization")


def session_token(request: Request) -> str:
    """The browser session's cookie token. Requests that send an API token never use one."""
    if _authorization(request) is not None:
        raise PermissionDeniedError(
            "This needs a browser session; it cannot be done with an API token"
        )
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise AuthenticationError("Not logged in")
    return token


SessionToken = Annotated[str, Depends(session_token)]

# Shown in the API docs, where Authorize takes a token from the Account page.
_bearer = HTTPBearer(
    auto_error=False,
    description="An API token from your Account page in runpad: `Authorization: Bearer rp_...`",
)


async def current_user(
    request: Request,
    response: Response,
    db: DbSession,
    _: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """The user behind an API token (Authorization header) or, without one, the browser
    session cookie. A request with an Authorization header is never authenticated by its
    cookie."""
    authorization = _authorization(request)
    if authorization is not None:
        scheme, _space, credential = authorization.partition(" ")
        if scheme.lower() != "bearer" or not credential.strip():
            raise AuthenticationError("Send the API token as Authorization: Bearer <token>")
        user = await api_tokens.resolve_token(db, credential.strip())
        if user is None:
            raise AuthenticationError("Invalid, expired, or revoked API token")
        return user
    token = session_token(request)
    resolved = await resolve_session(db, token)
    if resolved is None:
        raise AuthenticationError("Not logged in")
    user, refreshed = resolved
    if refreshed:
        set_session_cookie(request, response, token)
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def session_user(user: CurrentUser, _: SessionToken) -> User:
    """The logged-in user, through a browser session only: for managing API tokens and the
    password, which a leaked token must not be able to do."""
    return user


SessionUser = Annotated[User, Depends(session_user)]


async def require_admin(user: CurrentUser) -> User:
    if user.role != Role.ADMIN:
        raise PermissionDeniedError("Admin role required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def secret_cipher(request: Request) -> SecretCipher:
    return request.app.state.cipher


Cipher = Annotated[SecretCipher, Depends(secret_cipher)]


def get_runner(request: Request) -> Runner:
    return request.app.state.runner


RunnerDep = Annotated[Runner, Depends(get_runner)]


def get_poller(request: Request) -> Poller:
    return request.app.state.poller


PollerDep = Annotated[Poller, Depends(get_poller)]


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus


BusDep = Annotated[EventBus, Depends(get_bus)]
