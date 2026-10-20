"""Tile history: how each State's tone went over the last 24 hours.

Every poll extends a period of one tone (`state_periods`), or starts a new one when the tone
changes or polling stopped for a while (the app was down). Periods older than the window are
deleted hourly with old Runs. Tiles show the window as half-hour bars, each the worst tone
checked in it, and the share of the checked time that was not bad.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StatePeriod, StateTone
from app.schemas.features import TileHistory
from app.security import utcnow

WINDOW = timedelta(hours=24)
BUCKET = timedelta(minutes=30)
# Polls further apart than twice the interval plus this leave a gap in the history.
GAP_SLACK = timedelta(seconds=60)

# Worst first: a bar shows the worst tone checked in its half hour.
_SEVERITY = [StateTone.BAD, StateTone.WARN, StateTone.UNKNOWN, StateTone.NEUTRAL, StateTone.GOOD]

type Key = tuple[uuid.UUID, str]


async def record(
    db: AsyncSession,
    instance_id: uuid.UUID,
    key: str,
    tone: StateTone,
    now: datetime,
    interval_seconds: int,
) -> None:
    """Add one poll's tone to the history. The caller commits."""
    latest = await db.scalar(
        select(StatePeriod)
        .where(StatePeriod.feature_instance_id == instance_id, StatePeriod.key == key)
        .order_by(StatePeriod.ended_at.desc())
        .limit(1)
    )
    contiguous = latest is not None and now - latest.ended_at <= (
        2 * timedelta(seconds=interval_seconds) + GAP_SLACK
    )
    if latest is not None and contiguous and latest.tone == tone:
        latest.ended_at = now
        return
    db.add(
        StatePeriod(
            feature_instance_id=instance_id,
            key=key,
            tone=tone,
            # The tone changed somewhere since the last poll; it takes over from there.
            started_at=latest.ended_at if latest is not None and contiguous else now,
            ended_at=now,
        )
    )


async def histories(db: AsyncSession, keys: Iterable[Key]) -> dict[Key, TileHistory]:
    """The history of each (feature instance, State key), over the window ending now."""
    keys = set(keys)
    now = utcnow()
    periods: dict[Key, list[tuple[StateTone, datetime, datetime]]] = defaultdict(list)
    if keys:
        rows = await db.execute(
            select(
                StatePeriod.feature_instance_id,
                StatePeriod.key,
                StatePeriod.tone,
                StatePeriod.started_at,
                StatePeriod.ended_at,
            ).where(
                StatePeriod.feature_instance_id.in_({instance_id for instance_id, _ in keys}),
                StatePeriod.ended_at >= now - WINDOW,
            )
        )
        for instance_id, key, tone, started_at, ended_at in rows:
            periods[(instance_id, key)].append((tone, started_at, ended_at))
    return {key: summarize(periods[key], now) for key in keys}


def summarize(periods: list[tuple[StateTone, datetime, datetime]], now: datetime) -> TileHistory:
    """Half-hour bars over the window ending now, oldest first, and the share of the checked
    time that was not bad. Unknown (the check could not tell) counts as not checked."""
    start = now - WINDOW
    count = WINDOW // BUCKET
    seen: list[set[StateTone]] = [set() for _ in range(count)]
    durations: dict[StateTone, float] = defaultdict(float)
    for tone, started_at, ended_at in periods:
        if ended_at < start:
            continue
        begin = max(started_at, start)
        durations[tone] += (ended_at - begin).total_seconds()
        first = int((begin - start) // BUCKET)
        # A period ending where a bar starts did not reach into it.
        end = ended_at - timedelta(microseconds=1) if ended_at > begin else ended_at
        last = min(int((end - start) // BUCKET), count - 1)
        for index in range(first, last + 1):
            seen[index].add(tone)
    checked = sum(seconds for tone, seconds in durations.items() if tone != StateTone.UNKNOWN)
    return TileHistory(
        bucket_seconds=int(BUCKET.total_seconds()),
        buckets=[next((t for t in _SEVERITY if t in tones), None) for tones in seen],
        ok_percent=(
            round(100 * (checked - durations[StateTone.BAD]) / checked, 2) if checked else None
        ),
    )


async def purge(db: AsyncSession) -> None:
    """Delete periods that ended before the window."""
    await db.execute(delete(StatePeriod).where(StatePeriod.ended_at < utcnow() - WINDOW))
    await db.commit()
