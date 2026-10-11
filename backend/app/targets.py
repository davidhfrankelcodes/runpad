"""Targets: where Actions run. SSH host keys are pinned at creation."""

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import secret_store
from app.errors import ConflictError, DomainError, NotFoundError
from app.executors import http, ssh
from app.models import Secret, SecretKind, Target, TargetKind
from app.schemas.targets import (
    HttpConfig,
    SshConfig,
    SshConfigRead,
    TargetCreate,
    TargetRead,
    TargetUpdate,
)
from app.security import SecretCipher

_REQUIRED_SECRET_KIND = {TargetKind.SSH: SecretKind.SSH_KEY, TargetKind.HTTP: SecretKind.TEXT}
_CONFIG_MODEL: dict[TargetKind, type[BaseModel]] = {
    TargetKind.SSH: SshConfig,
    TargetKind.HTTP: HttpConfig,
}


def to_read(target: Target) -> TargetRead:
    config: SshConfigRead | HttpConfig
    if target.kind == TargetKind.SSH:
        stored = SshConfig.model_validate(target.config)
        config = SshConfigRead(
            **stored.model_dump(),
            host_key_fingerprint=ssh.parse_host_key(stored.host_key).fingerprint,
        )
    else:
        config = HttpConfig.model_validate(target.config)
    return TargetRead(
        id=target.id,
        name=target.name,
        kind=target.kind.value,
        secret_id=target.secret_id,
        config=config,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


async def _check_secret(db: AsyncSession, kind: TargetKind, secret_id: uuid.UUID) -> None:
    secret = await db.get(Secret, secret_id)
    if secret is None:
        raise DomainError("Secret not found")
    expected = _REQUIRED_SECRET_KIND[kind]
    if secret.kind != expected:
        raise DomainError(f"A {kind.value} target needs a {expected.value} secret")


def _dump_config(config: BaseModel) -> dict[str, Any]:
    return config.model_dump(mode="json")


async def _commit(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("A target with that name already exists") from exc


async def list_targets(db: AsyncSession) -> list[Target]:
    return list(await db.scalars(select(Target).order_by(Target.name)))


async def get_target(db: AsyncSession, target_id: uuid.UUID) -> Target:
    target = await db.get(Target, target_id)
    if target is None:
        raise NotFoundError("Target not found")
    return target


async def create_target(db: AsyncSession, body: TargetCreate) -> Target:
    kind = TargetKind(body.kind)
    if body.secret_id is not None:
        await _check_secret(db, kind, body.secret_id)
    target = Target(
        name=body.name, kind=kind, secret_id=body.secret_id, config=_dump_config(body.config)
    )
    db.add(target)
    await _commit(db)
    return target


async def update_target(db: AsyncSession, target_id: uuid.UUID, body: TargetUpdate) -> Target:
    target = await get_target(db, target_id)
    if body.name is not None:
        target.name = body.name
    if body.clear_secret:
        if target.kind == TargetKind.SSH:
            raise DomainError("An ssh target always needs a key")
        target.secret_id = None
    elif body.secret_id is not None:
        await _check_secret(db, target.kind, body.secret_id)
        target.secret_id = body.secret_id
    if body.config is not None:
        if not isinstance(body.config, _CONFIG_MODEL[target.kind]):
            raise DomainError(f"Config does not match a {target.kind.value} target")
        target.config = _dump_config(body.config)
    await _commit(db)
    return target


async def delete_target(db: AsyncSession, target_id: uuid.UUID) -> None:
    await db.delete(await get_target(db, target_id))
    await db.commit()


async def ssh_endpoint(db: AsyncSession, cipher: SecretCipher, target: Target) -> ssh.SshEndpoint:
    config = SshConfig.model_validate(target.config)
    if target.secret_id is None:
        raise DomainError(f"Target {target.name!r} has no SSH key")
    secret = await secret_store.get_secret(db, target.secret_id)
    return ssh.SshEndpoint(
        host=config.host,
        port=config.port,
        username=config.username,
        host_key=config.host_key,
        private_key=secret_store.reveal(cipher, secret),
    )


async def http_endpoint(
    db: AsyncSession, cipher: SecretCipher, target: Target
) -> http.HttpEndpoint:
    config = HttpConfig.model_validate(target.config)
    token = None
    if target.secret_id is not None:
        token = secret_store.reveal(cipher, await secret_store.get_secret(db, target.secret_id))
    return http.HttpEndpoint(
        base_url=str(config.base_url), verify_tls=config.verify_tls, bearer_token=token
    )


async def check_connection(
    db: AsyncSession, cipher: SecretCipher, target_id: uuid.UUID
) -> ssh.ConnectionCheck:
    target = await get_target(db, target_id)
    if target.kind == TargetKind.SSH:
        return await ssh.check_connection(await ssh_endpoint(db, cipher, target))
    return await http.check_connection(await http_endpoint(db, cipher, target))


async def scan_host_key(host: str, port: int) -> ssh.HostKey:
    try:
        return await ssh.scan_host_key(host, port)
    except (OSError, TimeoutError, ssh.asyncssh.Error) as exc:
        raise DomainError(f"Could not read the host key from {host}:{port}: {exc}") from exc
