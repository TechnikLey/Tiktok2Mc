"""Base plugin class that eliminates boilerplate across all plugins.

Usage
-----
    from core.base_plugin import BasePlugin

    class MyPlugin(BasePlugin):
        PLUGIN_NAME = "my-plugin"
        DEFAULT_PORT = 29190

        def on_command(self, command: str, args: dict):
            if command == "start":
                self.state["running"] = True

        def on_tick(self):
            # Called once per second (override if needed)
            pass

    if __name__ == "__main__":
        MyPlugin().run()
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core import parse_args, get_base_dir
from core.plugin_config import load_plugin_config
from core.theme import load_plugin_theme, theme_css

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

_API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:29185/api/v1")
_SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")


def _api_url(path: str) -> str:
    return f"{_API_BASE}/{path.lstrip('/')}"


# ---------------------------------------------------------------------------
#  BasePlugin
# ---------------------------------------------------------------------------

class BasePlugin:
    """Abstract base for TikTok2MC plugins.

    Handles lifecycle boilerplate:
    - Config loading from ``plugin.json`` + ``config.yaml``
    - Theme loading + CSS generation
    - API client setup (``PluginAPIClient``)
    - Command polling (long-poll with ``?wait=1``)
    - State push to API
    - Window state load/save
    - Overlay HTML registration
    - pywebview window management

    Subclasses **must** define ``PLUGIN_NAME``.
    """

    PLUGIN_NAME: str = ""
    DEFAULT_PORT: int = 29190

    def __init__(self):
        if not self.PLUGIN_NAME:
            raise RuntimeError("PLUGIN_NAME must be set on subclass")

        self._args = parse_args()
        self._base_dir = get_base_dir()
        self._plugin_dir = Path(__file__).resolve().parent
        self._data_dir = (self._base_dir.parent / "data").resolve()
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._state_file = self._data_dir / f"window_state_{self.PLUGIN_NAME}.json"
        self._window_state = self._load_window_state()

        self._cfg = load_plugin_config(self._plugin_dir)
        self._port = self._cfg.get("port", self.DEFAULT_PORT)
        self._server_host = _SERVER_HOST

        self._theme = load_plugin_theme(self._cfg, self.PLUGIN_NAME)
        self._theme_style = theme_css(self._theme)
        self._bg_color = self._theme.get("background", "#000000")

        self._state: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._running = True

        # Command dispatch table — subclasses register handlers here
        self._handlers: dict[str, Any] = {}

    # -- properties --------------------------------------------------------

    @property
    def state(self) -> dict[str, Any]:
        """Thread-safe access to plugin state (used by ``_push_state``)."""
        with self._lock:
            return dict(self._state)

    @state.setter
    def state(self, value: dict[str, Any]):
        with self._lock:
            self._state = dict(value)

    @property
    def config(self) -> dict[str, Any]:
        return dict(self._cfg)

    @property
    def theme_style(self) -> str:
        return self._theme_style

    @property
    def bg_color(self) -> str:
        return self._bg_color

    @property
    def gui_hidden(self) -> bool:
        return getattr(self._args, "gui_hidden", False)

    # -- window state -------------------------------------------------------

    def _load_window_state(self) -> dict[str, int]:
        if self._state_file.exists():
            try:
                with self._state_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {
                        "width": max(data.get("width", 600), 200),
                        "height": max(data.get("height", 300), 100),
                    }
            except Exception as e:
                log.warning("[%s] Failed to load window state: %s", self.PLUGIN_NAME, e)
        return {"width": 600, "height": 300}

    def save_window_state(self, width: int, height: int) -> None:
        try:
            with self._state_file.open("w", encoding="utf-8") as f:
                json.dump({"width": width, "height": height}, f)
        except Exception as e:
            log.warning("[%s] Failed to save window state: %s", self.PLUGIN_NAME, e)

    # -- API helpers --------------------------------------------------------

    def api_post(self, path: str, data: dict[str, Any]) -> bool:
        """POST JSON data to the central API."""
        try:
            body = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                _api_url(path), data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            return True
        except Exception as e:
            log.warning("[%s] API POST %s failed: %s", self.PLUGIN_NAME, path, e)
            return False

    def api_get(self, path: str, timeout: int = 5) -> dict[str, Any] | None:
        """GET JSON data from the central API."""
        try:
            req = urllib.request.Request(_api_url(path))
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as e:
            log.warning("[%s] API GET %s failed: %s", self.PLUGIN_NAME, path, e)
            return None

    def push_state(self) -> None:
        """Push current ``self.state`` to the API state endpoint."""
        self.api_post(f"/plugins/{self.PLUGIN_NAME}/state", {"state": self.state})

    def send_command(self, target_plugin: str, command: str, args: dict[str, Any] | None = None) -> bool:
        """Send a command to another plugin via the API."""
        payload = {"command": command, "args": args or {}}
        return self.api_post(f"/plugins/{target_plugin}/command", payload)

    def register_overlay(self, html: str) -> None:
        """Register overlay HTML with the central API."""
        self.api_post(f"/plugins/{self.PLUGIN_NAME}/overlay-html", {"html": html})

    # -- command polling ----------------------------------------------------

    def register_handler(self, command: str, callback):
        """Register a command handler.  ``callback`` receives ``(args: dict)``."""
        self._handlers[command] = callback

    def _command_polling_loop(self):
        """Background thread: long-poll commands from the API and dispatch."""
        while self._running:
            result = self.api_get(
                f"/plugins/{self.PLUGIN_NAME}/commands?wait=1", timeout=35
            )
            if not result:
                time.sleep(0.1)
                continue
            for entry in result.get("commands", []):
                cmd = entry.get("command", "")
                args = entry.get("args", {})
                handler = self._handlers.get(cmd)
                if handler:
                    try:
                        handler(args)
                    except Exception as e:
                        log.exception("[%s] Handler '%s' failed: %s", self.PLUGIN_NAME, cmd, e)
                else:
                    # Fall through to subclass ``on_command`` override
                    self.on_command(cmd, args)

    # -- tick loop ----------------------------------------------------------

    _HEARTBEAT_INTERVAL = 30  # seconds between heartbeat pings

    def _tick_loop(self):
        """Background thread: calls ``on_tick`` once per second.

        Also sends a heartbeat ping to the API every
        ``_HEARTBEAT_INTERVAL`` seconds so the health monitor does not
        mark an idle plugin as unhealthy.
        """
        heartbeat_counter = 0
        while self._running:
            try:
                self.on_tick()
            except Exception as e:
                log.exception("[%s] Tick failed: %s", self.PLUGIN_NAME, e)
            heartbeat_counter += 1
            if heartbeat_counter >= self._HEARTBEAT_INTERVAL:
                heartbeat_counter = 0
                try:
                    self.api_get(
                        f"/plugins/{self.PLUGIN_NAME}/commands?wait=0",
                        timeout=5,
                    )
                except Exception:
                    pass
            time.sleep(1)

    # -- subclass hooks -----------------------------------------------------

    def on_command(self, command: str, args: dict[str, Any]) -> None:
        """Called when an unhandled command arrives.

        Subclasses should override this or use ``register_handler()``.
        """
        log.debug("[%s] Unhandled command: %s %s", self.PLUGIN_NAME, command, args)

    def on_tick(self) -> None:
        """Called once per second in the background tick thread.

        Subclasses should override for periodic work (e.g. timer countdown).
        """
        pass

    def get_overlay_html(self) -> str:
        """Return the HTML string for the overlay.

        Subclasses **must** override this.
        """
        raise NotImplementedError("Subclasses must implement get_overlay_html()")

    # -- window / run -------------------------------------------------------

    def _start_threads(self):
        self._running = True
        tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
        tick_thread.start()

        poll_thread = threading.Thread(target=self._command_polling_loop, daemon=True)
        poll_thread.start()

        return tick_thread, poll_thread

    def run(self) -> None:
        """Main entry point: register overlay, start threads, open window."""
        html = self.get_overlay_html()
        self.register_overlay(html)

        tick_thread, poll_thread = self._start_threads()

        if not self.gui_hidden:
            try:
                import webview
                window = webview.create_window(
                    self.PLUGIN_NAME,
                    f"http://{_SERVER_HOST}:29185/api/v1/plugins/{self.PLUGIN_NAME}/overlay",
                    width=self._window_state["width"],
                    height=self._window_state["height"],
                    on_top=True,
                    background_color=self._bg_color,
                )
                webview.start()
            except ImportError:
                log.error("[%s] pywebview not installed — cannot open GUI window", self.PLUGIN_NAME)
        else:
            log.info(
                "[%s] Running in gui_hidden mode. Open "
                "http://%s:29185/api/v1/plugins/%s/overlay in OBS as a Browser Source.",
                self.PLUGIN_NAME, _SERVER_HOST, self.PLUGIN_NAME,
            )
            tick_thread.join()
