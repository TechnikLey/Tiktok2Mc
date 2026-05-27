import asyncio
import json
import logging

from fastapi import APIRouter, Query
from starlette.responses import StreamingResponse

from core.api.eventbus import event_bus

log = logging.getLogger(__name__)

router = APIRouter(tags=["Events"])


@router.get("/events/stream")
async def event_stream(
    types: str = Query(
        "",
        description="Comma-separated event types to subscribe to "
        "(empty = all events)",
    ),
):
    """Server-Sent Events (SSE) endpoint.

    Clients connect via ``EventSource`` and receive a stream of
    real-time events.  Optional ``?types=log,status`` filtering
    lets consumers subscribe to only the events they need.
    """

    filter_types = (
        [t.strip() for t in types.split(",") if t.strip()]
        if types
        else []
    )

    async def generate():
        q = event_bus.subscribe(*filter_types)
        try:
            # Signal that the connection is established
            yield f": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/events")
async def inject_event(body: dict):
    """Inject an event into the bus from any component.

    Expected format::

        {"type": "custom.event", "data": {"key": "value"}}
    """
    event_type = body.get("type", "external.event")
    data = body.get("data", {})
    await event_bus.publish(event_type, data)
    return {"status": "ok", "event": event_type}
