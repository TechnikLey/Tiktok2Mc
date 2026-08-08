import asyncio
import logging
import threading
import time
import uuid
from typing import Any

log = logging.getLogger(__name__)


class PluginStateStore:
    """Stores the latest state per plugin, thread-safe.

    Plugins push their current state via the EventBus
    (``plugin.{name}.state_update``) and the store caches the
    most recent value so SSE clients always receive the latest
    state on connection.
    """

    def __init__(self) -> None:
        self._states: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def set_state(self, name: str, state: dict[str, Any]) -> None:
        with self._lock:
            self._states[name] = state

    def get_state(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            return self._states.get(name)

    def clear(self, name: str) -> None:
        with self._lock:
            self._states.pop(name, None)


state_store = PluginStateStore()


class CommandQueue:
    """Per-plugin command queues with push notification support.

    Other components enqueue commands here via the API.
    Plugin processes can either poll ``GET /api/v1/plugins/{name}/commands``
    or use the long-polling variant ``?wait=1`` which blocks until
    a command arrives (zero-latency, no wasted CPU).
    """

    def __init__(self) -> None:
        self._queues: dict[str, list[dict[str, Any]]] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def enqueue(self, plugin_name: str, command: str, **kwargs: Any) -> str:
        cmd_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": cmd_id,
            "command": command,
            "args": kwargs,
            "timestamp": time.time(),
        }
        event: asyncio.Event | None = None
        with self._lock:
            self._queues.setdefault(plugin_name, []).append(entry)
            event = self._events.get(plugin_name)
        if event is not None and self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(event.set)
        return cmd_id

    def dequeue_all(self, plugin_name: str) -> list[dict[str, Any]]:
        with self._lock:
            cmds = self._queues.pop(plugin_name, [])
            event = self._events.get(plugin_name)
        if event is not None:
            event.clear()
        return cmds

    async def wait_for_commands(self, plugin_name: str, timeout: float = 30.0) -> None:
        """Block the current async task until a command is enqueued for *plugin_name*.

        Returns immediately if commands are already pending.
        Raises ``asyncio.TimeoutError`` if *timeout* elapses.
        """
        with self._lock:
            if self._queues.get(plugin_name):
                return
            if plugin_name not in self._events:
                self._events[plugin_name] = asyncio.Event()
            event = self._events[plugin_name]
        await asyncio.wait_for(event.wait(), timeout=timeout)

    def clear(self, plugin_name: str) -> None:
        with self._lock:
            self._queues.pop(plugin_name, None)
            self._events.pop(plugin_name, None)


command_queue = CommandQueue()


class OverlayHtmlStore:
    """Caches rendered overlay HTML for each plugin.

    Plugins POST their final rendered HTML on startup so the
    Main API can serve it at ``/api/v1/plugins/{name}/overlay``.
    """

    def __init__(self) -> None:
        self._html: dict[str, str] = {}
        self._lock = threading.Lock()

    def set_html(self, name: str, html: str) -> None:
        with self._lock:
            self._html[name] = html

    def get_html(self, name: str) -> str | None:
        with self._lock:
            return self._html.get(name)

    def clear(self, name: str) -> None:
        with self._lock:
            self._html.pop(name, None)


overlay_html_store = OverlayHtmlStore()
