"""Stored secrets: create, update, delete, and decrypt for use by executors."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import feature_instances
from app.errors import ConflictError, DomainError, NotFoundError
from app.executors.ssh import (
    SshKeyError,
    generate_private_key,
    normalize_private_key,
    public_key_of,
)
from app.models import Action, Secret, SecretKind, Target
from app.security import SecretCipher


def _prepare(kind: SecretKind, value: str) -> tuple[str, str | None]:
    """Validate a value and return (plaintext to store, public key)."""
    if kind == SecretKind.SSH_KEY:
        try:
            private_key = normalize_private_key(value)
        except SshKeyError as exc:
            raise DomainError(str(exc)) from exc
        return private_key, public_key_of(private_key)
    return value, None


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A secret with that name already exists") from exc


async def list_secrets(db: AsyncSession) -> list[Secret]:
    return list(await db.scalars(select(Secret).order_by(Secret.name)))


async def get_secret(db: AsyncSession, secret_id: uuid.UUID) -> Secret:
    secret = await db.get(Secret, secret_id)
    if secret is None:
        raise NotFoundError("Secret not found")
    return secret


async def create_secret(
    db: AsyncSession,
    cipher: SecretCipher,
    *,
    name: str,
    kind: SecretKind,
    value: str,
    description: str = "",
) -> Secret:
    plaintext, public_key = _prepare(kind, value)
    secret_id = uuid.uuid4()
    secret = Secret(
        id=secret_id,
        name=name,
        kind=kind,
        description=description,
        ciphertext=cipher.encrypt(plaintext, secret_id),
        public_key=public_key,
    )
    db.add(secret)
    await _commit(db)
    return secret


async def generate_ssh_key(
    db: AsyncSession, cipher: SecretCipher, *, name: str, description: str = ""
) -> Secret:
    return await create_secret(
        db,
        cipher,
        name=name,
        kind=SecretKind.SSH_KEY,
        value=generate_private_key(),
        description=description,
    )


async def update_secret(
    db: AsyncSession,
    cipher: SecretCipher,
    secret_id: uuid.UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    value: str | None = None,
) -> Secret:
    secret = await get_secret(db, secret_id)
    if name is not None:
        secret.name = name
    if description is not None:
        secret.description = description
    if value is not None:
        plaintext, secret.public_key = _prepare(secret.kind, value)
        secret.ciphertext = cipher.encrypt(plaintext, secret.id)
    await _commit(db)
    return secret


async def delete_secret(db: AsyncSession, secret_id: uuid.UUID) -> None:
    secret = await get_secret(db, secret_id)
    targets = sorted(await db.scalars(select(Target.name).where(Target.secret_id == secret_id)))
    if targets:
        raise ConflictError(f"Secret is used by targets: {', '.join(targets)}")
    actions = await db.scalars(
        select(Action.name).where(Action.secret_env.contains([{"secret_id": str(secret_id)}]))
    )
    if names := sorted(actions):
        raise ConflictError(f"Secret is used by actions: {', '.join(names)}")
    if names := sorted(await feature_instances.instances_using(db, secret_id=secret_id)):
        raise ConflictError(f"Secret is used by: {', '.join(names)}")
    await db.delete(secret)
    await db.commit()


def reveal(cipher: SecretCipher, secret: Secret) -> str:
    """Decrypt a secret for use by an executor. Never return this through the API."""
    return cipher.decrypt(secret.ciphertext, secret.id)
