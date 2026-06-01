#!/usr/bin/env python3
"""Core overlay subsystem.

Overlay has been promoted from a plugin to a built-in core subsystem.
This module manages:

* overlay configuration (read from the global config file)
* per-overlay circuit-breaker state
* HTML template rendering
* direct event-bus dispatch (no plugin indirection)
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
import threading
from pathlib import Path
from typing import Any

from core.theme import load_plugin_theme, theme_css
from core.yaml_utils import load_yaml
from core.paths import get_config_file

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Defaults
# ---------------------------------------------------------------------------

DEFAULT_OVERLAY_CONFIG: dict[str, Any] = {
    "enabled": True,
    "display_mode": "overwrite",
    "fade_in": 500,
    "fade_out": 500,
    "max_fails": 3,
    "cooldown": 10,
    "overlays": [{"name": "default"}],
    "theme": {
        "background": "#00FF00",
        "text": "#ffffff",
    },
}

# ---------------------------------------------------------------------------
#  HTML Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
{{ theme_style }}
        body {{
            margin: 0; padding: 0; overflow: hidden;
            {{ chroma_background }}
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            color: var(--text);
            font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
            text-shadow: 1px 1px 3px rgba(0,0,0,0.8), -1px -1px 3px rgba(0,0,0,0.8), 1px -1px 3px rgba(0,0,0,0.8), -1px 1px 3px rgba(0,0,0,0.8);
            -webkit-font-smoothing: antialiased;
        }}
        #container {{
            text-align: center;
            opacity: 0;
            transition: opacity {{ fade_in }}ms ease-in-out;
        }}
        h1 {{ font-size: 70px; margin: 0; color: var(--text); font-weight: 700; }}
        p {{ font-size: 30px; margin: 0; color: var(--text); font-weight: 400; }}
        .show {{ opacity: 1 !important; }}
    </style>
</head>
<body>
    <div id="container">
        <h1 id="title"></h1>
        <p id="subtitle"></p>
    </div>

    <script>
        const DISPLAY_MODE = "{{ display_mode }}";
        const FADE_IN_MS = {{ fade_in }};
        const FADE_OUT_MS = {{ fade_out }};
        const OVERLAY_NAME = "{{ overlay_name }}";

        const eventSource = new EventSource("/api/v1/overlay/stream");

        const container = document.getElementById('container');
        const titleEl = document.getElementById('title');
        const subtitleEl = document.getElementById('subtitle');

        let timeout = null;
        let showing = false;
        const messageQueue = [];

        function showMessage(data) {
            showing = true;
            titleEl.innerText = data.title;
            subtitleEl.innerText = data.subtitle;
            container.classList.add('show');

            clearTimeout(timeout);
            timeout = setTimeout(() => {
                container.style.transition = 'opacity ' + FADE_OUT_MS + 'ms ease-in-out';
                container.classList.remove('show');
                if (DISPLAY_MODE === "queue") {
                    setTimeout(() => {
                        showing = false;
                        container.style.transition = 'opacity ' + FADE_IN_MS + 'ms ease-in-out';
                        if (messageQueue.length > 0) {
                            showMessage(messageQueue.shift());
                        }
                    }, FADE_OUT_MS);
                } else {
                    showing = false;
                }
            }, data.duration * 1000);
        }

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.command !== "display") return;
            if (data.overlay_name && data.overlay_name !== OVERLAY_NAME) return;
            if (DISPLAY_MODE === "queue" && showing) {
                messageQueue.push(data);
            } else {
                showMessage(data);
            }
        };
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
#  Config
# ---------------------------------------------------------------------------

class OverlayConfig:
    """Overlay configuration backed by the global ``config.yaml``."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = threading.Lock()
        self.reload()

    def reload(self) -> None:
        """Load overlay settings from the global config file."""
        cfg_path = get_config_file()
        try:
            global_cfg = load_yaml(cfg_path) if cfg_path.exists() else {}
        except Exception as exc:
            log.warning("Failed to load global config for overlay: %s", exc)
            global_cfg = {}

        overlay_cfg = global_cfg.get("overlay", {})
        merged = copy.deepcopy(DEFAULT_OVERLAY_CONFIG)
        merged.update(overlay_cfg)

        with self._lock:
            self._data = merged

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)


# ---------------------------------------------------------------------------
#  Circuit-breaker client
# ---------------------------------------------------------------------------

class OverlayClient:
    """Per-overlay circuit breaker."""

    def __init__(self, name: str, max_fails: int, cooldown: int) -> None:
        self.name = name
        self.max_fails = max_fails
        self.cooldown = cooldown
        self._fail_count = 0
        self._last_fail_time = 0.0

    def get_cooldown_status(self) -> tuple[bool, int]:
        if self._fail_count >= self.max_fails:
            elapsed = time.time() - self._last_fail_time
            if elapsed < self.cooldown:
                return True, int(self.cooldown - elapsed)
            self._fail_count = 0
        return False, 0

    def mark_success(self) -> None:
        self._fail_count = 0

    def mark_failure(self) -> None:
        self._fail_count += 1
        self._last_fail_time = time.time()


# ---------------------------------------------------------------------------
#  Manager
# ---------------------------------------------------------------------------

class OverlayManager:
    """Central overlay manager — handles config, circuit breakers,
    HTML rendering, and direct event-bus dispatch.
    """

    def __init__(self) -> None:
        self.config = OverlayConfig()
        self.clients: dict[str, OverlayClient] = {}
        self._init_clients()

    def _init_clients(self) -> None:
        cfg = self.config.to_dict()
        def_fails = cfg.get("max_fails", 3)
        def_cooldown = cfg.get("cooldown", 10)

        clients: dict[str, OverlayClient] = {}
        for item in cfg.get("overlays", []):
            name = item.get("name")
            if not name:
                log.warning("Skipping overlay with missing name: %s", item)
                continue
            clients[name] = OverlayClient(
                name=name,
                max_fails=def_fails,
                cooldown=def_cooldown,
            )

        if "default" not in clients:
            clients["default"] = OverlayClient(
                name="default",
                max_fails=def_fails,
                cooldown=def_cooldown,
            )
            log.info("Created fallback 'default' overlay (not in config).")

        self.clients = clients
        log.info("Overlay manager initialised with %d overlay(s).", len(clients))

    def reload(self) -> None:
        """Reload configuration and rebuild clients."""
        self.config.reload()
        self._init_clients()

    # -- HTML rendering --------------------------------------------------

    def render_html(self, overlay_name: str = "default", chroma: bool = True) -> str:
        """Render the overlay HTML page for *overlay_name*."""
        cfg = self.config.to_dict()
        theme = load_plugin_theme(cfg, "overlay_text")
        theme_style = theme_css(theme)

        chroma_background = (
            f"background-color: {theme['background']};"
            if chroma
            else "background-color: transparent;"
        )
        return (
            HTML_TEMPLATE
            .replace("{{ theme_style }}", theme_style)
            .replace("{{ chroma_background }}", chroma_background)
            .replace("{{ display_mode }}", str(cfg.get("display_mode", "overwrite")))
            .replace("{{ fade_in }}", str(cfg.get("fade_in", 500)))
            .replace("{{ fade_out }}", str(cfg.get("fade_out", 500)))
            .replace("{{ overlay_name }}", overlay_name)
        )

    # -- Dispatch --------------------------------------------------------

    def dispatch(self, title: str, subtitle: str, duration: int, target_name: str) -> bool:
        """Send an overlay text message to *target_name*.

        Returns ``True`` if the message was accepted and published to the
        event bus, ``False`` if the overlay is unknown or in cooldown.
        """
        client = self.clients.get(target_name)
        if not client:
            log.error("Overlay '%s' not found.", target_name)
            return False

        blocked, remaining = client.get_cooldown_status()
        if blocked:
            log.warning("[%s] Circuit breaker active (%ss).", client.name, remaining)
            return False

        try:
            from core.api.eventbus import event_bus

            asyncio.run_coroutine_threadsafe(
                event_bus.publish(
                    "overlay.state_update",
                    {
                        "command": "display",
                        "overlay_name": target_name,
                        "title": title,
                        "subtitle": subtitle,
                        "duration": duration,
                    },
                ),
                _get_event_loop(),
            )
            client.mark_success()
            return True
        except Exception as exc:
            log.error("[OVERLAY] Dispatch to %s failed: %s", client.name, exc)
            client.mark_failure()
        return False


# ---------------------------------------------------------------------------
#  Event-loop helper
# ---------------------------------------------------------------------------

_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Tell the overlay manager which event loop to use for event-bus
    publishing.  Called once by the API server on startup."""
    global _loop
    _loop = loop


def _get_event_loop() -> asyncio.AbstractEventLoop:
    if _loop is not None:
        return _loop
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.get_event_loop_policy().get_event_loop()


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------

_manager: OverlayManager | None = None
_manager_lock = threading.Lock()


def get_overlay_manager() -> OverlayManager:
    """Return the global :class:`OverlayManager` singleton."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = OverlayManager()
    return _manager


def send_overlay_text(
    title: str,
    subtitle: str = "",
    duration: int = 3,
    overlay_name: str = "default",
) -> bool:
    """Public convenience wrapper around :meth:`OverlayManager.dispatch`."""
    return get_overlay_manager().dispatch(title, subtitle, duration, overlay_name)
