import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app import pads
from app.api.deps import BusDep, CurrentUser, DbSession
from app.events import Event
from app.models import Role, User

router = APIRouter(tags=["events"])


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
    """Server-Sent Events: `state` events carry a changed State (StateRead), `run` events a
    Run that started or finished (RunRead). Members get States of tiles on pads they can
    see, and their own Runs. The stream may end at any time; reconnect and refetch."""
    # The stream never ends on its own, so do not hold a database connection for it.
    await db.close()

    async def events() -> AsyncIterator[str]:
        with bus.subscribe() as subscription:
            yield ": connected\n\n"
            async for event in subscription.follow():
                if event is None:
                    yield ": keepalive\n\n"
                elif await _visible(request, user, event):
                    yield f"event: {event.name}\ndata: {json.dumps(event.data)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
