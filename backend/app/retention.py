"""Instance settings, and deleting Runs older than the retention period.

Runs are the audit log, so they are only ever deleted here: finished Runs whose start is
older than the admin-chosen retention period (30 days by default). Runs still in progress are
never deleted.
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import state_history
from app.models import AppSettings, Run, RunStatus
from app.schemas.app_settings import AppSettingsRead, AppSettingsUpdate
from app.security import utcnow

logger = logging.getLogger(__name__)

PURGE_INTERVAL_SECONDS = 3600


async def get_settings(db: AsyncSession) -> AppSettings:
    """The settings row, created with the defaults on first use."""
    settings = await db.scalar(select(AppSettings))
    if settings is not None:
        return settings
    db.add(AppSettings())
    try:
        await db.commit()
    except IntegrityError:  # Another request created it first.
        await db.rollback()
    return (await db.scalars(select(AppSettings))).one()


def to_read(settings: AppSettings) -> AppSettingsRead:
    return AppSettingsRead.model_validate({"run_retention_days": settings.run_retention_days})


async def update_settings(db: AsyncSession, body: AppSettingsUpdate) -> AppSettings:
    settings = await get_settings(db)
    settings.run_retention_days = body.run_retention_days
    await db.commit()
    await purge_runs(db)
    return settings


async def purge_runs(db: AsyncSession) -> int:
    """Delete finished Runs older than the retention period. Returns how many."""
    days = (await get_settings(db)).run_retention_days
    if days is None:
        return 0
    result = await db.execute(
        delete(Run).where(
            Run.started_at < utcnow() - timedelta(days=days),
            Run.status != RunStatus.RUNNING,
        )
    )
    await db.commit()
    deleted = result.rowcount or 0  # type: ignore[attr-defined]
    if deleted:
        logger.info("Deleted %d runs older than %d days", deleted, days)
    return deleted


class RetentionTask:
    """Purges old Runs at startup and then every hour."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="run-retention")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self) -> None:
        while True:
            try:
                async with self._sessionmaker() as db:
                    await purge_runs(db)
                    await state_history.purge(db)
            except Exception:
                logger.exception("Deleting old runs and tile history failed; trying again later")
            await asyncio.sleep(PURGE_INTERVAL_SECONDS)
