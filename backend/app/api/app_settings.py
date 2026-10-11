from fastapi import APIRouter

from app import retention
from app.api.deps import AdminUser, CurrentUser, DbSession
from app.schemas.app_settings import AppSettingsRead, AppSettingsUpdate

router = APIRouter(tags=["settings"])


@router.get("/settings")
async def get_settings(_: CurrentUser, db: DbSession) -> AppSettingsRead:
    """Instance-wide settings, such as how long runs are kept."""
    return retention.to_read(await retention.get_settings(db))


@router.put("/settings")
async def update_settings(body: AppSettingsUpdate, _: AdminUser, db: DbSession) -> AppSettingsRead:
    """Change instance-wide settings. Shortening run retention deletes older runs at once."""
    return retention.to_read(await retention.update_settings(db, body))
