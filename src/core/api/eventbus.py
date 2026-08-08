import asyncio
import logging
import threading
import time
from collections import defaultdict
from typing import Any

from core.error_codes import CORE_0006
from core.health_monitor import get_health_monitor

log = logging.getLogger(__name__)

ALL_EVENTS = "*"


class EventBus:
    """In-memory publish/subscribe event bus.

    Components publish events by type.  Consumers subscribe to one or
    more types and receive events asynchronously via ``asyncio.Queue``.

    This is the foundation for real-time GUI updates (dashboard, log
    viewer, status changes) and replaces the current per-plugin SSE
    approach over time.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Subscribe / unsubscribe
    # ------------------------------------------------------------------

    def subscribe(self, *event_types: str) -> asyncio.Queue:
        """Return an ``asyncio.Queue`` that receives all matching events.

        When called with no arguments the queue receives **all** events.
        When given one or more type strings it only receives those types.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        with self._lock:
            if not event_types:
                self._subscribers[ALL_EVENTS].append(q)
            else:
                for t in event_types:
                    self._subscribers[t].append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a queue from all subscriber lists."""
        with self._lock:
            for queues in self._subscribers.values():
                try:
                    queues.remove(q)
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        """Deliver an event to all matching subscribers asynchronously."""
        with self._lock:
            targets = list(self._subscribers.get(event_type, []))
            targets.extend(self._subscribers.get(ALL_EVENTS, []))

        msg: dict[str, Any] = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
        }

        for q in targets:
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning("Event queue full, dropping %s event", event_type)
                try:
                    get_health_monitor().record_error(
                        "eventbus",
                        f"{CORE_0006.code}: Queue full, dropping {event_type}",
                    )
                except Exception as e:  # best-effort health reporting
                    log.debug("Health reporting for dropped event failed: %s", e)


# Module-level singleton — import and use directly.
event_bus = EventBus()
