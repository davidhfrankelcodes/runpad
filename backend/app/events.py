"""In-process publish/subscribe for State and Run changes, streamed at /api/v1/events.

Publishing never blocks. A subscriber that falls too far behind is dropped; its stream
ends, and the browser reconnects and refetches.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, Literal

QUEUE_SIZE = 256
KEEPALIVE_SECONDS = 15


@dataclass(frozen=True)
class Event:
    name: Literal["state", "run"]
    data: dict[str, Any]  # JSON-ready.
    # Who may see it: State events go to those who can see a tile of the instance;
    # Run events to admins and the user who started the Run.
    feature_instance_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


@dataclass(eq=False)
class Subscription:
    queue: asyncio.Queue[Event | None] = field(
        default_factory=lambda: asyncio.Queue(maxsize=QUEUE_SIZE)
    )
    dropped: bool = False

    async def follow(self) -> AsyncIterator[Event | None]:
        """Yield events until the bus closes or drops this subscriber. Yields None while
        idle, so callers can send keepalives."""
        while True:
            try:
                async with asyncio.timeout(KEEPALIVE_SECONDS):
                    event = await self.queue.get()
            except TimeoutError:
                yield None
                continue
            if event is None or self.dropped:
                return
            yield event


class EventBus:
    def __init__(self) -> None:
        self._subscriptions: set[Subscription] = set()

    @contextmanager
    def subscribe(self) -> Iterator[Subscription]:
        subscription = Subscription()
        self._subscriptions.add(subscription)
        try:
            yield subscription
        finally:
            self._subscriptions.discard(subscription)

    def publish(self, event: Event) -> None:
        for subscription in list(self._subscriptions):
            try:
                subscription.queue.put_nowait(event)
            except asyncio.QueueFull:
                subscription.dropped = True
                self._subscriptions.discard(subscription)

    def close(self) -> None:
        """End every stream (on shutdown)."""
        for subscription in list(self._subscriptions):
            subscription.dropped = True
            # When the queue is full, the stream ends as soon as it reads its next event.
            with suppress(asyncio.QueueFull):
                subscription.queue.put_nowait(None)
        self._subscriptions.clear()
