from fastapi import APIRouter

from app.api import (
    actions,
    app_settings,
    auth,
    events,
    features,
    pads,
    runs,
    secrets,
    targets,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(pads.router)
api_router.include_router(targets.router)
api_router.include_router(secrets.router)
api_router.include_router(actions.router)
api_router.include_router(features.router)
api_router.include_router(runs.router)
api_router.include_router(events.router)
api_router.include_router(app_settings.router)
