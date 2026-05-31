"""Plugin health monitoring.

Provides a passive health monitor that periodically checks enabled
plugins via the registry and marks stale/unreachable plugins as
unhealthy.  Active process-level health checking is done by
``start.py`` which calls into this module via the API.
"""

import time
import asyncio
import logging
from threading import Lock

from core.api.registry import get_registry
from core.api.eventbus import event_bus

log = logging.getLogger(__name__)

_HEALTH_CHECK_INTERVAL = 15.0
_HEARTBEAT_TIMEOUT = 60.0


class PluginHealthMonitor:
    """Background health monitor for plugins.

    Runs in the API server as an asyncio task.  Periodically checks
    that enabled plugins have recent heartbeats and updates registry
    health status accordingly.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._lock = Lock()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())
        log.info("Plugin health monitor started")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
            log.info("Plugin health monitor stopped")

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
                self._check_health()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("Health monitor check failed")

    def _check_health(self) -> None:
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
                    plugin.name, age, new_status,
                )
                registry.update(plugin.name, health_status=new_status)


_health_monitor: PluginHealthMonitor | None = None


def get_health_monitor() -> PluginHealthMonitor:
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = PluginHealthMonitor()
    return _health_monitor
