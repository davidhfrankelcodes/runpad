import uuid

from fastapi import APIRouter, status

from app import secret_store
from app.api.deps import AdminUser, Cipher, DbSession
from app.schemas.secrets import SecretCreate, SecretRead, SecretUpdate, SshKeyGenerate

router = APIRouter(prefix="/secrets", tags=["secrets"])


@router.get("")
async def list_secrets(_: AdminUser, db: DbSession) -> list[SecretRead]:
    return [SecretRead.model_validate(s) for s in await secret_store.list_secrets(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_secret(
    body: SecretCreate, _: AdminUser, db: DbSession, cipher: Cipher
) -> SecretRead:
    secret = await secret_store.create_secret(
        db, cipher, name=body.name, kind=body.kind, value=body.value, description=body.description
    )
    return SecretRead.model_validate(secret)


@router.post("/generate-ssh-key", status_code=status.HTTP_201_CREATED)
async def generate_ssh_key(
    body: SshKeyGenerate, _: AdminUser, db: DbSession, cipher: Cipher
) -> SecretRead:
    """Generate an ed25519 key pair. Copy `public_key` into the host's authorized_keys."""
    secret = await secret_store.generate_ssh_key(
        db, cipher, name=body.name, description=body.description
    )
    return SecretRead.model_validate(secret)


@router.patch("/{secret_id}")
async def update_secret(
    secret_id: uuid.UUID, body: SecretUpdate, _: AdminUser, db: DbSession, cipher: Cipher
) -> SecretRead:
    secret = await secret_store.update_secret(
        db, cipher, secret_id, name=body.name, description=body.description, value=body.value
    )
    return SecretRead.model_validate(secret)


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(secret_id: uuid.UUID, _: AdminUser, db: DbSession) -> None:
    await secret_store.delete_secret(db, secret_id)
