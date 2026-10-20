import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app import pads
from app.api.deps import BusDep, CurrentUser, DbSession, authenticate
from app.errors import AuthenticationError, PermissionDeniedError
from app.events import Event
from app.models import Role, User

router = APIRouter(tags=["events"])

# How often an open stream checks that its session or token is still valid, and the user's
# role: a demoted, deactivated, or logged-out user stops receiving events within this.
RECHECK_SECONDS = 15


async def _recheck(request: Request) -> User | None:
    """The stream's user now, or None if it may no longer receive events."""
    try:
        async with request.app.state.sessionmaker() as db:
            user, _ = await authenticate(request, db)
    except (AuthenticationError, PermissionDeniedError):
        return None
    return user


async def _visible(request: Request, user: User, event: Event) -> bool:
    if user.role == Role.ADMIN:
        return True
    if event.name == "run":
        return event.user_id == user.id  # Members see their own Runs, as in /runs.
    if event.feature_instance_id is None:
        return False
    async with request.app.state.sessionmaker() as db:
        return await pads.can_see_instance(db, user, event.feature_instance_id)


@router.get(
    "/events",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_events(
    request: Request, user: CurrentUser, db: DbSession, bus: BusDep
) -> StreamingResponse:
    """Server-Sent Events: `ready` once subscribed (refetch what you show, since earlier
    changes were not sent), then `state` events with a changed State (StateRead) and `run`
    events with a Run that started or finished (RunRead). Members get States of tiles on
    pads they can see, and their own Runs. The stream may end at any time; reconnect."""
    # The stream never ends on its own, so do not hold a database connection for it.
    await db.close()

    async def events() -> AsyncIterator[str]:
        viewer, checked = user, time.monotonic()
        with bus.subscribe() as subscription:
            # Sent once subscribed: anything that changed before this was missed, so the
            # client should (re)load what it shows.
            yield "event: ready\ndata: {}\n\n"
            async for event in subscription.follow():
                if time.monotonic() - checked >= RECHECK_SECONDS:
                    rechecked = await _recheck(request)
                    if rechecked is None:
                        return
                    viewer, checked = rechecked, time.monotonic()
                if event is None:
                    yield ": keepalive\n\n"
                elif await _visible(request, viewer, event):
                    yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
