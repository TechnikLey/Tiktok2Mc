"""Plugin health monitoring.

Provides a passive health monitor that periodically checks enabled
plugins via the registry and marks stale/unreachable plugins as
unhealthy.  Active process-level health checking is done by
``start.py`` which calls into this module via the API.
"""

import asyncio
import logging
import time

from core.api.registry import get_registry

log = logging.getLogger(__name__)

_HEALTH_CHECK_INTERVAL = 15.0
# Heartbeat timeout must be comfortably longer than the longest idle poll
# cycle.  BasePlugin long-polls commands with a 35s timeout; if no commands
# arrive the poll returns empty and records a heartbeat every ~35s.  A 90s
# timeout gives a 2.5x safety margin before marking a plugin unhealthy.
_HEARTBEAT_TIMEOUT = 90.0


class PluginHealthMonitor:
    """Background health monitor for plugins.

    Runs in the API server as an asyncio task.  Periodically checks
    that enabled plugins have recent heartbeats and updates registry
    health status accordingly.
    """

    def __init__(self) -> None:
        """Create an idle monitor; the check task starts in :meth:`start`."""
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the periodic health-check task.

Calling this while a task already exists is a no-op. The task begins with
a sleep, so the first check runs one interval after startup."""

        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())
        log.info("Plugin health monitor started")

    async def stop(self) -> None:
        """Cancel the periodic health-check task, if any.

The task is cancelled without being awaited and the reference is cleared,
allowing a later :meth:`start` to create a fresh task."""

        if self._task is not None:
            self._task.cancel()
            self._task = None
            log.info("Plugin health monitor stopped")

    async def _run(self) -> None:
        """Run health checks until cancelled.

Each iteration sleeps for the check interval and then evaluates the
registry. Unexpected errors are logged and the loop continues, so a single
failed check cannot stop monitoring."""

        while True:
            try:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
                self._check_health()
            except asyncio.CancelledError:
                break
            except Exception:  # health monitor loop must never die
                log.exception("Health monitor check failed")

    def _check_health(self) -> None:
        """Update registry health from heartbeat ages.

Only enabled plugins with a recorded heartbeat are considered. A heartbeat
older than the timeout marks the plugin ``unhealthy`` unless it is already
``dead``. A fresh heartbeat promotes ``starting``, ``unknown``,
``unhealthy``, or ``dead`` plugins to ``healthy``; plugins already marked
healthy are left untouched."""

        registry = get_registry()
        now = time.time()
        for plugin in registry.list():
            if not plugin.enabled:
                continue
            if plugin.last_heartbeat is None:
                continue
            age = now - plugin.last_heartbeat
            if age > _HEARTBEAT_TIMEOUT and plugin.health_status != "dead":
                new_status = "unhealthy"
                log.warning(
                    "Plugin '%s' heartbeat timeout (%.0fs) — marking %s",
                    plugin.name,
                    age,
                    new_status,
                )
                registry.update(plugin.name, health_status=new_status)
            elif age <= _HEARTBEAT_TIMEOUT and plugin.health_status in (
                "starting",
                "unknown",
                "unhealthy",
                "dead",
            ):
                # Promote to healthy once a recent heartbeat is seen.
                if plugin.health_status in ("unhealthy", "dead"):
                    log.info(
                        "Plugin '%s' recovered (was %s) — marking healthy",
                        plugin.name,
                        plugin.health_status,
                    )
                registry.update(plugin.name, health_status="healthy")


_health_monitor: PluginHealthMonitor | None = None


def get_plugin_health_monitor() -> PluginHealthMonitor:
    """Singleton accessor for the plugin heartbeat monitor.

    Deliberately NOT named ``get_health_monitor`` — that name belongs to
    ``core.health_monitor.get_health_monitor`` (process-level health).
    """
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = PluginHealthMonitor()
    return _health_monitor
