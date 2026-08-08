"""TikTok live connection state tracker.

The TikTok bridge (``main.py``) reports its live connection status to the
API server via ``tiktok.live_status`` events (``POST /api/v1/events``).
This module records the latest state in memory so the GUI can query it
through ``GET /status`` and receive realtime updates over SSE.

Real TikTok events arriving on the API event bus are also recorded as
activity, but **test triggers** (``test: true`` or ``source: trigger_tester``)
are explicitly ignored so a simulated event never looks like a live stream.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from core.api.eventbus import event_bus

log = logging.getLogger(__name__)

EVENT_TYPE = "tiktok.live_status"

# Treat the reported state as stale (unknown) after this many seconds without
# a bridge update — e.g. the bridge process died or restarted silently.
STALE_AFTER_SECONDS = 90.0


def _is_test_event(data: dict[str, Any]) -> bool:
    """Return True for simulated events that must not affect live status."""
    return bool(data.get("test")) or data.get("source") == "trigger_tester"


class TikTokLiveTracker:
    """Thread-safe store of the last reported TikTok live status."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connected: bool | None = None
        self._last_update: float = 0.0
        self._last_event_at: float = 0.0
        self._source: str = ""
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool, source: str = "") -> None:
        ts = time.time()
        with self._lock:
            self._connected = bool(connected)
            self._last_update = ts
            if connected:
                self._last_event_at = ts
            self._source = source

    def record_event(self) -> None:
        with self._lock:
            self._last_event_at = time.time()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            connected = self._connected
            last_update = self._last_update
            last_event_at = self._last_event_at
            source = self._source
        if connected is not None and (now - last_update) > STALE_AFTER_SECONDS:
            connected = None
        return {
            "tiktok_live": connected,
            "tiktok_live_last_update": last_update,
            "tiktok_live_last_event": last_event_at,
            "tiktok_live_source": source,
        }

    # ------------------------------------------------------------------
    # EventBus subscription
    # ------------------------------------------------------------------

    async def _consume(self) -> None:
        q = event_bus.subscribe()
        try:
            while True:
                msg = await q.get()
                try:
                    self._handle(msg)
                except Exception:  # one bad event must not kill the consumer loop
                    log.debug("[TIKTOK-LIVE] Error handling event", exc_info=True)
                finally:
                    q.task_done()
        except asyncio.CancelledError:
            pass

    def _handle(self, msg: dict[str, Any]) -> None:
        event_type = msg.get("type", "")
        data = msg.get("data", {}) or {}
        if event_type == EVENT_TYPE:
            self.set_connected(
                bool(data.get("connected")),
                source=str(data.get("source", "")),
            )
        elif event_type.startswith("tiktok."):
            if _is_test_event(data):
                return
            self.record_event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

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
_tracker: TikTokLiveTracker | None = None


def get_tiktok_live_tracker() -> TikTokLiveTracker:
    global _tracker
    if _tracker is None:
        _tracker = TikTokLiveTracker()
    return _tracker
