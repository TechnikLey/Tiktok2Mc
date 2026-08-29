#!/usr/bin/env python3
"""Core overlay subsystem (API side).

Manages overlay configuration, circuit-breaker state, HTML template rendering,
and direct event-bus dispatch.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import threading
from typing import Any

from core.overlay_base import (
    DEFAULT_OVERLAY_CONFIG,
    OverlayManagerBase,
    _load_overlay_config,
)
from core.theme import load_plugin_theme, sanitize_css_value, theme_css

log = logging.getLogger(__name__)


def _escape_js_string(value: str) -> str:
    """Escape *value* for a double-quoted JS string literal inside an HTML
    ``<script>`` block: neutralises quotes, backslashes and ``</script>``
    breakouts without corrupting the surrounding markup."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("<", "\\x3c")
        .replace(">", "\\x3e")
    )


# ---------------------------------------------------------------------------
#  HTML Template
# ---------------------------------------------------------------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <style>
{{ theme_style }}
        body {
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
        }
        #container {
            text-align: center;
            opacity: 0;
            transition: opacity {{ fade_in }}ms ease-in-out;
        }
        h1 { font-size: 70px; margin: 0; color: var(--text); font-weight: 700; }
        p { font-size: 30px; margin: 0; color: var(--text); font-weight: 400; }
        .show { opacity: 1 !important; }
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
        merged = DEFAULT_OVERLAY_CONFIG.copy()
        merged.update(_load_overlay_config())

        with self._lock:
            self._data = merged

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)


# ---------------------------------------------------------------------------
#  Manager (inherits shared base)
# ---------------------------------------------------------------------------


class OverlayManager(OverlayManagerBase):
    """Central overlay manager — handles config, circuit breakers,
    HTML rendering, and direct event-bus dispatch.
    """

    def __init__(self) -> None:
        self.config = OverlayConfig()
        super().__init__()

    def reload(self) -> None:
        """Reload configuration and rebuild clients."""
        self.config.reload()
        super().reload()

    # -- HTML rendering --------------------------------------------------

    def render_html(
        self,
        overlay_name: str = "default",
        chroma: bool = True,
        theme_overrides: dict | None = None,
    ) -> str:
        """Render the overlay HTML page for *overlay_name*.

        If *theme_overrides* is given it is merged on top of the resolved
        theme so callers can preview live theme changes without saving.
        """
        cfg = self.config.to_dict()
        theme = load_plugin_theme(cfg, "overlay_text")
        if theme_overrides:
            theme = {**theme, **theme_overrides}
        theme_style = theme_css(theme)

        chroma_background = (
            f"background-color: {sanitize_css_value(theme['background'])};"
            if chroma
            else "background-color: transparent;"
        )
        return (
            HTML_TEMPLATE.replace("{{ theme_style }}", theme_style)
            .replace("{{ chroma_background }}", chroma_background)
            .replace(
                "{{ display_mode }}",
                _escape_js_string(str(cfg.get("display_mode", "overwrite"))),
            )
            .replace("{{ fade_in }}", str(cfg.get("fade_in", 500)))
            .replace("{{ fade_out }}", str(cfg.get("fade_out", 500)))
            .replace("{{ overlay_name }}", _escape_js_string(overlay_name))
        )

    # -- Dispatch --------------------------------------------------------

    def dispatch(
        self, title: str, subtitle: str, duration: int, target_name: str
    ) -> bool:
        """Send an overlay text message to *target_name*.

        Returns ``True`` if the message was accepted and published to the
        event bus, ``False`` if the overlay is unknown or in cooldown.
        """
        client = self.get_client(target_name)
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
        except Exception as exc:  # dispatch must never throw to trigger engine
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
