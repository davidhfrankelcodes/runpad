from fastapi import APIRouter

from app.api import auth, secrets, targets, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(targets.router)
api_router.include_router(secrets.router)
