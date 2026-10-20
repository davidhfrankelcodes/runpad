"""State polling: runs each Feature instance's probe on an interval and stores the result.

Probes go through the same target resolution and executors as Runs. The latest result is
kept on the instance's State rows (value, detail, checked_at), and changes are published as
events. A probe is recorded as a Run, attributed to the system, only when it changes a
State's value or tone: recording every probe (one per instance every 30 seconds) would bury
real button presses in the run history.
"""

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import feature_instances, runs, state_history
from app.errors import DomainError
from app.events import Event, EventBus
from app.executors import get_executor
from app.executors.base import ExecutionError, ExecutionRequest
from app.features import get_feature
from app.features.base import Probe, ProbeResult, StateValue
from app.models import FeatureInstance, Run, RunStatus, State
from app.runner import Redactor, prepare_request
from app.schemas.features import StateRead
from app.security import SecretCipher, utcnow

logger = logging.getLogger(__name__)

TICK_SECONDS = 1.0
MAX_CONCURRENT_PROBES = 8
PROBE_OUTPUT_LIMIT_BYTES = 64 * 1024


def state_event(state: State) -> Event:
    return Event(
        name="state",
        data=StateRead.model_validate(state).model_dump(mode="json"),
        feature_instance_id=state.feature_instance_id,
    )


class Poller:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        cipher: SecretCipher,
        bus: EventBus,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._cipher = cipher
        self._bus = bus
        self._next_due: dict[uuid.UUID, float] = {}
        self._in_flight: dict[uuid.UUID, asyncio.Task[None]] = {}
        self._wake = asyncio.Event()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROBES)
        self._task: asyncio.Task[None] | None = None
        self._refreshes: set[asyncio.Task[None]] = set()

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="poller")

    async def stop(self) -> None:
        tasks = [
            t for t in [self._task, *self._in_flight.values(), *self._refreshes] if t is not None
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def poll_soon(self, instance_id: uuid.UUID) -> None:
        """Poll an instance on the next tick, for example after its config changed."""
        self._next_due[instance_id] = 0
        self._wake.set()

    def refresh_after_run(self, instance_id: uuid.UUID) -> None:
        """A Run of a button instance finished: poll the tiles it may have changed, those of
        the same feature with the same config, right away."""
        task = asyncio.create_task(self._refresh_related(instance_id))
        self._refreshes.add(task)
        task.add_done_callback(self._refreshes.discard)

    async def _refresh_related(self, instance_id: uuid.UUID) -> None:
        try:
            async with self._sessionmaker() as db:
                related = await feature_instances.related_tile_instances(db, instance_id)
        except Exception:
            logger.exception("Finding the tiles of feature instance %s failed", instance_id)
            return
        for related_id in related:
            self.poll_soon(related_id)

    async def _run(self) -> None:
        while True:
            try:
                await self._schedule()
            except Exception:
                logger.exception("Polling schedule failed")
            self._wake.clear()
            with suppress(TimeoutError):
                async with asyncio.timeout(TICK_SECONDS):
                    await self._wake.wait()

    async def _schedule(self) -> None:
        async with self._sessionmaker() as db:
            rows = (
                await db.execute(
                    select(FeatureInstance.id, FeatureInstance.feature_id, FeatureInstance.item)
                )
            ).all()
        now = time.monotonic()
        polled: set[uuid.UUID] = set()
        for instance_id, feature_id, item_key in rows:
            feature = get_feature(feature_id)
            item = feature.item(item_key) if feature else None
            # Only tiles show State; button instances are never polled.
            if feature is None or feature.poll is None or item is None or item.kind != "tile":
                continue
            polled.add(instance_id)
            if instance_id in self._in_flight or self._next_due.get(instance_id, 0) > now:
                continue
            self._next_due[instance_id] = now + feature.poll.interval_seconds
            task = asyncio.create_task(self._guarded(instance_id), name=f"poll-{instance_id}")
            self._in_flight[instance_id] = task
            task.add_done_callback(lambda _, i=instance_id: self._in_flight.pop(i, None))
        for instance_id in set(self._next_due) - polled:  # Deleted instances.
            del self._next_due[instance_id]

    async def _guarded(self, instance_id: uuid.UUID) -> None:
        try:
            async with self._semaphore:
                await self.poll(instance_id)
        except Exception:
            logger.exception("Polling feature instance %s failed", instance_id)

    async def poll(self, instance_id: uuid.UUID) -> None:
        """Probe one instance now and store what it reports."""
        async with self._sessionmaker() as db:
            instance = await db.get(FeatureInstance, instance_id)
            if instance is None:
                return
            feature = get_feature(instance.feature_id)
            if feature is None or feature.poll is None:
                return
            polled_config = instance.config
            try:
                config = feature.ConfigModel.model_validate(polled_config)
            except ValidationError:
                logger.warning("Feature instance %s has an invalid config", instance_id)
                return
            probe = feature.poll.probe(config)
            try:
                request, secrets = await prepare_request(
                    db,
                    self._cipher,
                    name=instance.name,
                    executor=probe.executor,
                    target_id=probe.target_id,
                    spec=probe.spec,
                    specs=[],
                    args={},
                    secret_env=probe.secret_env,
                )
            except DomainError as exc:
                result = ProbeResult(exit_code=None, output="", error=exc.detail)
            else:
                result = None
        # The database session is closed while the probe runs.
        started_at = utcnow()
        if result is None:
            result = await self._execute(probe, request, secrets)
        # A probe may report several States (host resources: load, memory, disk); this
        # instance shows one.
        values = [v for v in feature.poll.parse(config, result) if v.key == instance.item]
        await self._store(
            instance_id, polled_config, values, result, started_at, feature.poll.interval_seconds
        )

    async def _execute(
        self, probe: Probe, request: ExecutionRequest, secrets: list[str]
    ) -> ProbeResult:
        redactor = Redactor(secrets)
        output = bytearray()

        async def on_output(data: bytes) -> None:
            output.extend(data[: PROBE_OUTPUT_LIMIT_BYTES - len(output)])

        def text() -> str:
            return redactor.redact(output.decode(errors="replace"))

        deadline = asyncio.timeout(probe.timeout_seconds)
        try:
            async with deadline:
                exit_code = await get_executor(probe.executor).execute(request, on_output)
        except TimeoutError as exc:
            message = (
                f"No answer within {probe.timeout_seconds} seconds"
                if deadline.expired()
                else redactor.redact(str(exc) or "Timed out")
            )
            return ProbeResult(exit_code=None, output=text(), error=message)
        except ExecutionError as exc:
            return ProbeResult(exit_code=None, output=text(), error=redactor.redact(str(exc)))
        return ProbeResult(exit_code=exit_code, output=text())

    async def _store(
        self,
        instance_id: uuid.UUID,
        polled_config: dict[str, Any],
        values: list[StateValue],
        result: ProbeResult,
        started_at: datetime,
        interval_seconds: int,
    ) -> None:
        now = utcnow()
        changed: list[State] = []
        transitioned = False  # A new State, or a new value or tone.
        async with self._sessionmaker() as db:
            # Locked so a concurrent config change either finishes first (and the result
            # is discarded as stale) or waits for this one.
            instance = await db.get(FeatureInstance, instance_id, with_for_update=True)
            if instance is None or instance.config != polled_config:
                return
            query = select(State).where(State.feature_instance_id == instance_id)
            existing = {state.key: state for state in await db.scalars(query)}
            for reported in values:
                value, detail = reported.value[:64], reported.detail[:1000]
                state = existing.get(reported.key)
                if state is None:
                    state = State(feature_instance_id=instance_id, key=reported.key)
                    db.add(state)
                    state.changed_at = now
                    changed.append(state)
                    transitioned = True
                else:
                    if (state.value, state.tone) != (value, reported.tone):
                        state.changed_at = now
                        transitioned = True
                    if (state.value, state.tone, state.detail) != (value, reported.tone, detail):
                        changed.append(state)
                state.value, state.tone, state.detail = value, reported.tone, detail
                state.checked_at = now
                await state_history.record(
                    db, instance_id, reported.key, reported.tone, now, interval_seconds
                )
            run = _probe_run(instance, result, started_at, now) if transitioned else None
            if run is not None:
                db.add(run)
            try:
                await db.commit()
            except IntegrityError:
                return  # The instance was deleted concurrently.
        for state in changed:
            self._bus.publish(state_event(state))
        if run is not None:
            self._bus.publish(
                Event(name="run", data=runs.to_read(run, None).model_dump(mode="json"))
            )


def _probe_run(
    instance: FeatureInstance, result: ProbeResult, started_at: datetime, finished_at: datetime
) -> Run:
    """The record of a probe that changed a State. No Action ran, so action_id is None."""
    ok = result.error is None and result.exit_code == 0
    return Run(
        action_id=None,
        action_name=f"Check {instance.name}"[:64],
        user_id=None,
        args={},
        status=RunStatus.SUCCEEDED if ok else RunStatus.FAILED,
        started_at=started_at,
        finished_at=finished_at,
        exit_code=result.exit_code,
        output=result.output,
        error=result.error,
    )
