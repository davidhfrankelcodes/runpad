import uuid

from fastapi import APIRouter, status

from app import feature_instances
from app.api.deps import AdminUser, DbSession, PollerDep
from app.schemas.features import (
    FeatureInstanceBatchCreate,
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
    return await feature_instances.to_reads(db, await feature_instances.list_instances(db))


@router.post("/feature-instances", status_code=status.HTTP_201_CREATED)
async def create_instance(
    body: FeatureInstanceCreate, user: AdminUser, db: DbSession, poller: PollerDep
) -> FeatureInstanceRead:
    """Add one item of a feature: its one button (and Action) or its one tile."""
    instance = await feature_instances.create_instance(db, user, body)
    poller.poll_soon(instance.id)
    return await feature_instances.to_read(db, instance)


@router.post("/feature-instances/batch", status_code=status.HTTP_201_CREATED)
async def create_instances(
    body: FeatureInstanceBatchCreate, user: AdminUser, db: DbSession, poller: PollerDep
) -> list[FeatureInstanceRead]:
    """Add several items of one feature with the same config, such as Start, Stop, and
    Status for one container. One instance each; all are added, or none."""
    instances = await feature_instances.create_instances(db, user, body)
    for instance in instances:
        poller.poll_soon(instance.id)
    return await feature_instances.to_reads(db, instances)


@router.get("/feature-instances/{instance_id}")
async def get_instance(instance_id: uuid.UUID, _: AdminUser, db: DbSession) -> FeatureInstanceRead:
    return await feature_instances.to_read(
        db, await feature_instances.get_instance(db, instance_id)
    )


@router.patch("/feature-instances/{instance_id}")
async def update_instance(
    instance_id: uuid.UUID,
    body: FeatureInstanceUpdate,
    _: AdminUser,
    db: DbSession,
    poller: PollerDep,
) -> FeatureInstanceRead:
    """Rename, or change the config and rebuild what it generated in place."""
    instance = await feature_instances.update_instance(db, instance_id, body)
    if body.config is not None:
        poller.poll_soon(instance.id)
    return await feature_instances.to_read(db, instance)


@router.delete("/feature-instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(instance_id: uuid.UUID, _: AdminUser, db: DbSession) -> None:
    """Delete the instance and everything it generated. Runs stay in the history."""
    await feature_instances.delete_instance(db, instance_id)
