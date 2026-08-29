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
        self._lock = threading.Lock()
        self._status: dict[str, Any] | None = None
        self._last_update: float = 0.0
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Mutation / query
    # ------------------------------------------------------------------

    def record(self, status: dict[str, Any]) -> None:
        with self._lock:
            self._status = dict(status)
            self._last_update = time.time()

    def snapshot(self) -> dict[str, Any] | None:
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
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._consume())

    async def stop(self) -> None:
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
    global _tracker
    if _tracker is None:
        _tracker = ChatbotStatusTracker()
    return _tracker
