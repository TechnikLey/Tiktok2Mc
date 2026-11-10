"""Dashboard Publisher — pushes live diagnostics to the EventBus for SSE clients.

This module runs a lightweight background task that periodically publishes
current system state (plugin health, ECM activity, etc.) as EventBus events.
Dashboard / GUI clients receive these via the existing SSE stream without
needing any extra endpoints.
"""

import asyncio
import logging
from typing import Any

from core.api.eventbus import event_bus
from core.api.plugin_overlay import state_store
from core.api.registry import get_registry
from core.api.task_utils import stop_task_safely

log = logging.getLogger(__name__)

PUSH_INTERVAL = 5.0


class DashboardPublisher:
    """Background task publishing periodic dashboard diagnostics."""

    def __init__(self) -> None:
        """Create a stopped publisher with no background task."""
        self._task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    #  Data gathering
    # ------------------------------------------------------------------

    @staticmethod
    def _build_plugin_states() -> dict[str, Any]:
        """Return a snapshot of current plugin states."""
        registry = get_registry()
        plugins = registry.list()
        states: dict[str, Any] = {}
        for p in plugins:
            cached = state_store.get_state(p.name)
            states[p.name] = {
                "name": p.name,
                "display_name": p.display_name or p.name,
                "enabled": p.enabled,
                "health_status": p.health_status,
                "version": p.version,
                "last_heartbeat": p.last_heartbeat,
                "cached_state": cached,
            }
        return states

    @staticmethod
    def _build_ecm_diagnostics() -> dict[str, Any] | None:
        """Return current Event-Command Mapper diagnostics."""
        try:
            from core.event_command_mapper import get_event_command_mapper

            return get_event_command_mapper().get_diagnostics()
        except Exception as exc:  # dashboard data is best-effort
            log.debug("[DASHBOARD] Could not fetch ECM diagnostics: %s", exc)
            return None

    # ------------------------------------------------------------------
    #  Push loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Publish dashboard snapshots once per :data:`PUSH_INTERVAL`.

        Plugin states are always published; ECM diagnostics only when available.
        Individual push failures are logged and do not stop the loop."""

        log.info("[DASHBOARD] Publisher started (interval %.1fs)", PUSH_INTERVAL)
        while self._running:
            try:
                await asyncio.sleep(PUSH_INTERVAL)
                if not self._running:
                    break

                plugin_states = self._build_plugin_states()
                ecm_diag = self._build_ecm_diagnostics()

                await event_bus.publish(
                    "dashboard.plugin_states",
                    {"plugins": plugin_states, "total": len(plugin_states)},
                )

                if ecm_diag is not None:
                    await event_bus.publish(
                        "dashboard.ecm_diagnostics",
                        ecm_diag,
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:  # push loop must survive individual failures
                log.warning("[DASHBOARD] Push error: %s", exc)
        log.info("[DASHBOARD] Publisher stopped")

    # ------------------------------------------------------------------
    #  Public lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background publisher if it is not already running."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Stop the publisher task (loop-safe).

        When the task was created on a foreign (e.g. already closed) event
        loop, awaiting it would block; :func:`stop_task_safely` only schedules
        the cancellation on the owning loop instead."""
        if not self._running:
            return
        self._running = False
        if self._task:
            await stop_task_safely(self._task)
            self._task = None


# Module-level singleton
_publisher: DashboardPublisher | None = None


def get_dashboard_publisher() -> DashboardPublisher:
    """Return the process-wide publisher, creating it on first use."""
    global _publisher
    if _publisher is None:
        _publisher = DashboardPublisher()
    return _publisher
