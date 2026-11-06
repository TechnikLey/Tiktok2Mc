"""Chatbot status tracker.

The TikTok bridge reports chatbot state via ``chatbot.status`` events
(``POST /api/v1/events``).  This module records the latest state in
memory so the GUI can query it through ``GET /chatbot/status`` and
receive realtime updates over SSE — same pattern as
:mod:`core.api.tiktok_live`.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from core.api.eventbus import event_bus

log = logging.getLogger(__name__)

EVENT_TYPE = "chatbot.status"

# Treat the reported state as stale (unknown) after this many seconds
# without a bridge update — e.g. the bridge process died or restarted.
STALE_AFTER_SECONDS = 90.0


class ChatbotStatusTracker:
    """Thread-safe store of the last reported chatbot status."""

    def __init__(self) -> None:
        """Create a tracker with no recorded status and no consumer task."""
        self._lock = threading.Lock()
        self._status: dict[str, Any] | None = None
        self._last_update: float = 0.0
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Mutation / query
    # ------------------------------------------------------------------

    def record(self, status: dict[str, Any]) -> None:
        """Store a copy of the latest status and its arrival time."""
        with self._lock:
            self._status = dict(status)
            self._last_update = time.time()

    def snapshot(self) -> dict[str, Any] | None:
        """Return the latest status, or ``None`` when it is stale or absent.

A status older than :data:`STALE_AFTER_SECONDS` is treated as unknown,
which hides state left behind by a dead bridge process. The stored
dictionary itself is returned, not a copy."""

        now = time.time()
        with self._lock:
            status = self._status
            last_update = self._last_update
        if status is not None and (now - last_update) > STALE_AFTER_SECONDS:
            return None
        return status

    # ------------------------------------------------------------------
    # EventBus subscription
    # ------------------------------------------------------------------

    async def _consume(self) -> None:
        """Record ``chatbot.status`` events until cancelled.

Malformed events are logged at debug level and skipped so the
subscription loop keeps running."""

        q = event_bus.subscribe(EVENT_TYPE)
        try:
            while True:
                msg = await q.get()
                try:
                    data = msg.get("data", {}) or {}
                    if isinstance(data, dict):
                        self.record(data)
                except Exception:  # one bad event must not kill the consumer loop
                    log.debug("[CHATBOT-STATUS] Error handling event", exc_info=True)
                finally:
                    q.task_done()
        except asyncio.CancelledError:
            pass

    def start(self) -> None:
        """Start the event consumer once.

Must be called from a running event loop."""

        if self._task is not None:
            return
        self._task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        """Cancel and await the consumer task, ignoring cancellation."""
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None


# Module-level singleton
_tracker: ChatbotStatusTracker | None = None


def get_chatbot_status_tracker() -> ChatbotStatusTracker:
    """Return the process-wide tracker, creating it on first use."""
    global _tracker
    if _tracker is None:
        _tracker = ChatbotStatusTracker()
    return _tracker
