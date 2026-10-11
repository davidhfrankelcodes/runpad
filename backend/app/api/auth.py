from fastapi import APIRouter, Request, Response, status

from app import users
from app.api.deps import (
    CurrentUser,
    DbSession,
    SessionToken,
    clear_session_cookie,
    set_session_cookie,
)
from app.schemas.users import (
    LoginRequest,
    PasswordChange,
    SetupRequest,
    SetupStatus,
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
    user = await users.authenticate(db, body.username, body.password)
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
