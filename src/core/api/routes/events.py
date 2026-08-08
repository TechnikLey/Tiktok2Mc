import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query
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
            yield ": connected\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
                    log.debug("SSE client disconnected abruptly: %s", exc)
                    break
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            log.debug("SSE transport closed: %s", exc)
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/events")
async def inject_event(body: dict):
    """Inject an event into the bus from any component.

    Expected format::

        {"type": "custom.event", "data": {"key": "value"}}
    """
    try:
        event_type = body.get("type", "external.event")
        data = body.get("data", {})
        if not isinstance(event_type, str):
            raise HTTPException(
                status_code=422, detail="'type' must be a string"
            )
        if not isinstance(data, dict):
            raise HTTPException(
                status_code=422, detail="'data' must be a dict"
            )
        await event_bus.publish(event_type, data)
        return {"status": "ok", "event": event_type}
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to inject event")
        raise HTTPException(status_code=500, detail=str(e))
