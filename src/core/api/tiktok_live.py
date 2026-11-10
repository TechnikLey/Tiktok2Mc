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
from core.api.task_utils import stop_task_safely

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
        """Create an unknown/empty live-status record.

        ``connected`` stays ``None`` until the bridge reports a state, which lets
        the GUI distinguish "unknown" from "disconnected"."""

        self._lock = threading.Lock()
        self._connected: bool | None = None
        self._last_update: float = 0.0
        self._last_event_at: float = 0.0
        self._source: str = ""
        self._task: asyncio.Task | None = None
        self._sub_q: asyncio.Queue | None = None  # released via unsubscribe

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def set_connected(self, connected: bool, source: str = "") -> None:
        """Record a reported connection state.

        Updates the report timestamp and source. A transition to connected also
        sets the last-event timestamp so a fresh connection counts as activity."""

        ts = time.time()
        with self._lock:
            self._connected = bool(connected)
            self._last_update = ts
            if connected:
                self._last_event_at = ts
            self._source = source

    def record_event(self) -> None:
        """Record that a non-test TikTok event was observed."""
        with self._lock:
            self._last_event_at = time.time()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return the current status fields for the API.

        If the last bridge update is older than ``STALE_AFTER_SECONDS``, the
        reported connection is downgraded to ``None`` (unknown) while the original
        timestamps and source are still returned."""

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
        """Process events from the API event bus until cancelled.

        Every event is acknowledged with ``task_done``. Handler errors are logged
        and do not terminate the consumer; cancellation exits quietly."""

        q = self._sub_q = event_bus.subscribe()
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
        finally:
            event_bus.unsubscribe(q)
            self._sub_q = None

    def _handle(self, msg: dict[str, Any]) -> None:
        """Update tracker state from one bus event.

        ``tiktok.live_status`` events set the connection state. Other ``tiktok.*``
        events refresh the activity timestamp unless they are marked as test
        events, which are ignored so simulations never look like live traffic."""

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
        """Start the background consumer task.

        Calling this while a task already exists is a no-op."""

        if self._task is not None:
            return
        self._task = asyncio.create_task(self._consume())

    def _release_sub_q(self) -> None:
        """Release the event-bus subscription when abandoning the task.

        Used by :meth:`stop` via :func:`stop_task_safely`: when the consumer
        task lives on a foreign event loop its own cleanup cannot be awaited,
        so the subscription is unsubscribed directly here instead. Idempotent
        — unsubscribing an already-released queue is a no-op."""

        if self._sub_q is not None:
            event_bus.unsubscribe(self._sub_q)
            self._sub_q = None

    async def stop(self) -> None:
        """Stop the consumer task (loop-safe) and release its subscription."""
        if self._task is None:
            return
        await stop_task_safely(self._task, on_abandoned=self._release_sub_q)
        self._task = None


# Module-level singleton
_tracker: TikTokLiveTracker | None = None


def get_tiktok_live_tracker() -> TikTokLiveTracker:
    """Return the global :class:`TikTokLiveTracker` singleton."""
    global _tracker
    if _tracker is None:
        _tracker = TikTokLiveTracker()
    return _tracker
