"""Bridge-side overlay HTTP client.

Thin wrapper that POSTs overlay commands to the core API endpoint
``/api/v1/overlay/display``.  Shares config loading and circuit-breaker
logic with the API-side overlay subsystem via :mod:`core.overlay_base`.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from core.overlay_base import (
    OverlayManagerBase,
)

log = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:29185/api/v1"


# ---------------------------------------------------------------------------
#  Manager (inherits shared base, adds HTTP dispatch)
# ---------------------------------------------------------------------------


class OverlayManager(OverlayManagerBase):
    """Bridge-side overlay manager — uses HTTP POST to the core API."""

    def dispatch(
        self, title: str, subtitle: str, duration: int, target_name: str
    ) -> bool:
        """Send an overlay text message to *target_name* via HTTP POST.

        Returns ``True`` if the message was accepted by the API,
        ``False`` if the overlay is unknown or in cooldown.
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
            body = json.dumps(
                {
                    "title": title,
                    "subtitle": subtitle,
                    "duration": duration,
                    "overlay_name": target_name,
                }
            ).encode()
            req = urllib.request.Request(
                f"{API_BASE}/overlay/display",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=5)
            client.mark_success()
            return True
        except urllib.error.HTTPError as e:
            if e.code == 429:
                log.warning("[%s] Server reported cooldown.", client.name)
            else:
                log.error(
                    "[OVERLAY] Command to %s failed: HTTP %s", client.name, e.code
                )
            client.mark_failure()
        except (urllib.error.URLError, OSError, TypeError) as e:
            log.error("[OVERLAY] Command to %s failed: %s", client.name, e)
            client.mark_failure()
        return False


# ---------------------------------------------------------------------------
#  Singleton + public API
# ---------------------------------------------------------------------------

_manager: OverlayManager | None = None
_manager_lock = None


def _get_manager() -> OverlayManager:
    global _manager, _manager_lock
    if _manager is None:
        import threading

        if _manager_lock is None:
            _manager_lock = threading.Lock()
        with _manager_lock:
            if _manager is None:
                _manager = OverlayManager()
    return _manager


def send_overlay_text(
    title: str,
    subtitle: str = "",
    duration: int = 3,
    overlay_name: str = "default",
    plugin_name: str = "overlay-text",
) -> bool:
    """Send overlay text via the core API.

    The *plugin_name* parameter is kept for backward compatibility but
    is no longer used — overlay is a core subsystem, not a plugin.
    """
    return _get_manager().dispatch(title, subtitle, duration, overlay_name)
