"""Bidirectional WebSocket endpoint streaming events and accepting subscriptions."""

import asyncio
import json
import logging
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.api.api_key import get_api_key
from core.api.eventbus import event_bus

log = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])

_LOCALHOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Bidirectional WebSocket endpoint.

    The client receives a stream of all events (same data as the SSE
    endpoint) and can optionally send JSON commands::

        {"type": "subscribe", "events": ["log", "status"]}

    By default the client receives **all** event types.
    """
    api_key = get_api_key()
    if api_key:
        client_host = ws.client.host if ws.client else ""
        if client_host not in _LOCALHOSTS:
            req_key = ws.query_params.get("key", "")
            if not secrets.compare_digest(req_key, api_key):
                await ws.close(code=4401, reason="Unauthorized")
                return

    await ws.accept()

    # Shared mutable state guarded by a lock so reader and writer agree
    # on which queue is active.  ``nonlocal`` reassignment alone races
    # with the writer's ``await q.get()``.
    state = {
        "q": event_bus.subscribe(),
    }
    state_lock = asyncio.Lock()

    async def reader():
        """Read subscription commands from the client until it disconnects.

Malformed JSON is ignored. A ``subscribe`` command atomically replaces the
active event queue; an empty event list means all event types. The old
queue is unsubscribed only after the new one is installed so the writer
never reads from a dead queue."""

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
        """Forward queued events to the client until it disconnects.

Sends a ``{"type": "ping"}`` message after 30 seconds without an event so
proxies keep the socket open and disconnects are detected promptly."""

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
    except Exception:  # socket teardown errors are expected; nothing to surface
        pass
    finally:
        async with state_lock:
            event_bus.unsubscribe(state["q"])
