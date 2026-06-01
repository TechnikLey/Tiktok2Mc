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
from core.api.registry import get_registry
from core.api.plugin_overlay import state_store

log = logging.getLogger(__name__)

PUSH_INTERVAL = 5.0


class DashboardPublisher:
    """Background task publishing periodic dashboard diagnostics."""

    def __init__(self) -> None:
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
        except Exception as exc:
            log.debug("[DASHBOARD] Could not fetch ECM diagnostics: %s", exc)
            return None

    # ------------------------------------------------------------------
    #  Push loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
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

                    # Also push a dedicated reactions-activity event
                    # that the GUI can show as a live feed
                    recent = ecm_diag.get("recent_dispatches", [])
                    if recent:
                        await event_bus.publish(
                            "dashboard.reactions_activity",
                            {"recent": recent},
                        )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.warning("[DASHBOARD] Push error: %s", exc)
        log.info("[DASHBOARD] Publisher stopped")

    # ------------------------------------------------------------------
    #  Public lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


# Module-level singleton
_publisher: DashboardPublisher | None = None


def get_dashboard_publisher() -> DashboardPublisher:
    global _publisher
    if _publisher is None:
        _publisher = DashboardPublisher()
    return _publisher
