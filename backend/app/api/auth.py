import uuid

from fastapi import APIRouter, Request, Response, status

from app import api_tokens, login_limits, users
from app.api.deps import (
    CurrentUser,
    DbSession,
    SessionToken,
    SessionUser,
    clear_session_cookie,
    set_session_cookie,
)
from app.config import Settings
from app.errors import AuthenticationError
from app.schemas.api_tokens import ApiTokenCreate, ApiTokenCreated, ApiTokenRead
from app.schemas.users import (
    Appearance,
    LoginRequest,
    PasswordChange,
    SetupRequest,
    SetupStatus,
    ThemeUpdate,
    UserRead,
)
from app.security import SESSION_COOKIE, create_session, delete_session

router = APIRouter(tags=["auth"])


@router.get("/setup")
async def get_setup_status(db: DbSession) -> SetupStatus:
    return SetupStatus(required=await users.setup_required(db))


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def complete_setup(
    body: SetupRequest, request: Request, response: Response, db: DbSession
) -> UserRead:
    """Create the first admin and log them in. Only works while no users exist."""
    user = await users.create_first_admin(db, body.username, body.password)
    set_session_cookie(request, response, await create_session(db, user))
    return UserRead.model_validate(user)


@router.post("/auth/login")
async def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession
) -> UserRead:
    """Log in. After too many failures from your IP or for the username, answers 429 with
    Retry-After until older failures expire."""
    ip = login_limits.client_ip(request)
    await login_limits.check(db, ip, body.username)
    try:
        user = await users.authenticate(db, body.username, body.password)
    except AuthenticationError:
        await db.rollback()
        await login_limits.record_failure(db, ip, body.username)
        raise
    await login_limits.clear(db, ip, body.username)
    set_session_cookie(request, response, await create_session(db, user))
    return UserRead.model_validate(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db: DbSession) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await delete_session(db, token)
    clear_session_cookie(response)


@router.get("/auth/me")
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChange, user: CurrentUser, token: SessionToken, db: DbSession
) -> None:
    """Change your own password. Logs out your other sessions."""
    await users.change_own_password(db, user, body.current_password, body.new_password, token)


@router.get("/appearance")
async def appearance(request: Request) -> Appearance:
    """Public, so the login screen can use the last theme too."""
    settings: Settings = request.app.state.settings
    return Appearance(themepark_url=settings.themepark_url)


@router.put("/auth/theme")
async def set_theme(body: ThemeUpdate, user: CurrentUser, db: DbSession) -> UserRead:
    """Choose your own theme.park theme, or null for runpad's own colors."""
    user.theme = body.theme
    await db.commit()
    return UserRead.model_validate(user)


@router.get("/auth/tokens")
async def list_api_tokens(user: SessionUser, db: DbSession) -> list[ApiTokenRead]:
    """Your API tokens, newest first. Needs a browser session, not an API token."""
    return await api_tokens.list_tokens(db, user)


@router.post("/auth/tokens", status_code=status.HTTP_201_CREATED)
async def create_api_token(
    body: ApiTokenCreate, user: SessionUser, db: DbSession
) -> ApiTokenCreated:
    """Create an API token that acts as you. The token is in this response only. Needs a
    browser session, not an API token."""
    return await api_tokens.create_token(db, user, body)


@router.delete("/auth/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_token(token_id: uuid.UUID, user: SessionUser, db: DbSession) -> None:
    """Revoke one of your API tokens; it stops working at once. Needs a browser session."""
    await api_tokens.revoke_token(db, user, token_id)
