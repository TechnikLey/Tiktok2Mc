import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.api.eventbus import event_bus

log = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Bidirectional WebSocket endpoint.

    The client receives a stream of all events (same data as the SSE
    endpoint) and can optionally send JSON commands::

        {"type": "subscribe", "events": ["log", "status"]}

    By default the client receives **all** event types.
    """
    await ws.accept()

    q = event_bus.subscribe()
    subscribed_to_all = True
    active_types: set[str] = set()

    async def reader():
        nonlocal subscribed_to_all, active_types
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    cmd = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if cmd.get("type") == "subscribe":
                    event_bus.unsubscribe(q)
                    types = cmd.get("events", [])
                    if types:
                        active_types = set(types)
                        subscribed_to_all = False
                        q = event_bus.subscribe(*types)
                    else:
                        subscribed_to_all = True
                        q = event_bus.subscribe()
                        active_types.clear()
        except WebSocketDisconnect:
            pass

    async def writer():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    await ws.send_json(msg)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "ping"})
        except WebSocketDisconnect:
            pass
        finally:
            event_bus.unsubscribe(q)

    try:
        await asyncio.gather(reader(), writer())
    except Exception:
        event_bus.unsubscribe(q)
