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

    # Shared mutable state guarded by a lock so reader and writer agree
    # on which queue is active.  ``nonlocal`` reassignment alone races
    # with the writer's ``await q.get()``.
    state = {
        "q": event_bus.subscribe(),
    }
    state_lock = asyncio.Lock()

    async def reader():
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    cmd = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if cmd.get("type") == "subscribe":
                    types = cmd.get("events", [])
                    async with state_lock:
                        old_q = state["q"]
                        if types:
                            new_q = event_bus.subscribe(*types)
                        else:
                            new_q = event_bus.subscribe()
                        state["q"] = new_q
                    # Unsubscribe the old queue after installing the new
                    # one so the writer never reads from a dead queue.
                    event_bus.unsubscribe(old_q)
        except WebSocketDisconnect:
            pass

    async def writer():
        try:
            while True:
                async with state_lock:
                    current_q = state["q"]
                try:
                    msg = await asyncio.wait_for(current_q.get(), timeout=30)
                    await ws.send_json(msg)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "ping"})
        except WebSocketDisconnect:
            pass

    try:
        await asyncio.gather(reader(), writer())
    except Exception:  # noqa: BLE001  # socket teardown errors are expected; nothing to surface
        pass
    finally:
        async with state_lock:
            event_bus.unsubscribe(state["q"])
