import uuid

from fastapi import APIRouter, status

from app import feature_instances
from app.api.deps import AdminUser, DbSession
from app.schemas.features import (
    FeatureInstanceCreate,
    FeatureInstanceRead,
    FeatureInstanceUpdate,
    FeatureRead,
)

router = APIRouter(tags=["features"])


@router.get("/features")
async def list_features(_: AdminUser) -> list[FeatureRead]:
    """The catalog: every Feature that can be enabled, with its setup form schema."""
    return feature_instances.catalog()


@router.get("/feature-instances")
async def list_instances(_: AdminUser, db: DbSession) -> list[FeatureInstanceRead]:
    return [
        FeatureInstanceRead.model_validate(i) for i in await feature_instances.list_instances(db)
    ]


@router.post("/feature-instances", status_code=status.HTTP_201_CREATED)
async def create_instance(
    body: FeatureInstanceCreate, user: AdminUser, db: DbSession
) -> FeatureInstanceRead:
    """Enable a Feature: validate its config and create its Actions (and Buttons)."""
    return FeatureInstanceRead.model_validate(
        await feature_instances.create_instance(db, user, body)
    )


@router.get("/feature-instances/{instance_id}")
async def get_instance(instance_id: uuid.UUID, _: AdminUser, db: DbSession) -> FeatureInstanceRead:
    return FeatureInstanceRead.model_validate(await feature_instances.get_instance(db, instance_id))


@router.patch("/feature-instances/{instance_id}")
async def update_instance(
    instance_id: uuid.UUID, body: FeatureInstanceUpdate, _: AdminUser, db: DbSession
) -> FeatureInstanceRead:
    """Rename, or change the config and rebuild the generated Actions in place."""
    return FeatureInstanceRead.model_validate(
        await feature_instances.update_instance(db, instance_id, body)
    )


@router.delete("/feature-instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(instance_id: uuid.UUID, _: AdminUser, db: DbSession) -> None:
    """Delete the instance and everything it generated. Runs stay in the history."""
    await feature_instances.delete_instance(db, instance_id)
