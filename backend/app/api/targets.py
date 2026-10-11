import uuid

from fastapi import APIRouter, status

from app import targets
from app.api.deps import AdminUser, Cipher, DbSession
from app.schemas.targets import (
    ConnectionTestResult,
    HostKeyRead,
    HostKeyScanRequest,
    TargetCreate,
    TargetRead,
    TargetUpdate,
)

router = APIRouter(prefix="/targets", tags=["targets"])


@router.get("")
async def list_targets(_: AdminUser, db: DbSession) -> list[TargetRead]:
    return [targets.to_read(t) for t in await targets.list_targets(db)]


@router.post("/scan-host-key")
async def scan_host_key(body: HostKeyScanRequest, _: AdminUser) -> HostKeyRead:
    """Read an SSH server's host key. Confirm the fingerprint, then pin it on the target."""
    key = await targets.scan_host_key(body.host, body.port)
    return HostKeyRead(
        public_key=key.public_key, algorithm=key.algorithm, fingerprint=key.fingerprint
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_target(body: TargetCreate, _: AdminUser, db: DbSession) -> TargetRead:
    return targets.to_read(await targets.create_target(db, body))


@router.get("/{target_id}")
async def get_target(target_id: uuid.UUID, _: AdminUser, db: DbSession) -> TargetRead:
    return targets.to_read(await targets.get_target(db, target_id))


@router.patch("/{target_id}")
async def update_target(
    target_id: uuid.UUID, body: TargetUpdate, _: AdminUser, db: DbSession
) -> TargetRead:
    return targets.to_read(await targets.update_target(db, target_id, body))


@router.delete("/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(target_id: uuid.UUID, _: AdminUser, db: DbSession) -> None:
    await targets.delete_target(db, target_id)


@router.post("/{target_id}/test")
async def test_target(
    target_id: uuid.UUID, _: AdminUser, db: DbSession, cipher: Cipher
) -> ConnectionTestResult:
    """Connect and authenticate (SSH) or send a GET to the base URL (HTTP). Runs no command."""
    result = await targets.check_connection(db, cipher, target_id)
    return ConnectionTestResult(ok=result.ok, message=result.message)
