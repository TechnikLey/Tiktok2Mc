import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from ruamel.yaml.error import YAMLError

from core.paths import get_config_file
from core.yaml_utils import load_yaml

log = logging.getLogger(__name__)

API_BASE = "http://127.0.0.1:29185/api/v1"


# ---------------------------------------------------------------------------
#  Config helper (global config)
# ---------------------------------------------------------------------------


def _load_overlay_config() -> dict[str, Any]:
    """Load overlay settings from the global config file."""
    cfg_path = get_config_file()
    try:
        global_cfg = load_yaml(cfg_path) if cfg_path.exists() else {}
    except (OSError, ValueError, YAMLError) as exc:
        log.warning("Failed to load global config for overlay: %s", exc)
        global_cfg = {}
    return global_cfg.get("overlay", {})


# ---------------------------------------------------------------------------
#  Circuit-breaker client
# ---------------------------------------------------------------------------


class OverlayClient:
    def __init__(self, name, max_fails, cooldown):
        self.name = name
        self.max_fails = max_fails
        self.cooldown = cooldown
        self._fail_count = 0
        self._last_fail_time = 0

    def get_cooldown_status(self):
        if self._fail_count >= self.max_fails:
            elapsed = time.time() - self._last_fail_time
            if elapsed < self.cooldown:
                return True, int(self.cooldown - elapsed)
            self._fail_count = 0
        return False, 0

    def mark_success(self):
        self._fail_count = 0

    def mark_failure(self):
        self._fail_count += 1
        self._last_fail_time = time.time()


# ---------------------------------------------------------------------------
#  Manager
# ---------------------------------------------------------------------------


class OverlayManager:
    """Client-side overlay manager that reads from the global config and
    dispplays overlay text via the core API endpoint.
    """

    def __init__(self):
        self.clients = {}
        self.load_config()

    def load_config(self):
        cfg = _load_overlay_config()

        def_fails = cfg.get("max_fails", 3)
        def_cooldown = cfg.get("cooldown", 10)

        for item in cfg.get("overlays", []):
            name = item.get("name")
            if not name:
                log.warning("Skipping overlay with missing name: %s", item)
                continue
            self.clients[name] = OverlayClient(
                name=name,
                max_fails=def_fails,
                cooldown=def_cooldown,
            )

        if "default" not in self.clients:
            self.clients["default"] = OverlayClient(
                name="default",
                max_fails=def_fails,
                cooldown=def_cooldown,
            )
            log.info("Created fallback 'default' overlay (not in config).")

        log.info("Loaded %d overlays from global config", len(self.clients))

    def dispatch(self, title, subtitle, duration, target_name):
        client = self.clients.get(target_name)
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

_manager = None
_manager_lock = threading.Lock()


def send_overlay_text(
    title,
    subtitle,
    duration=3,
    overlay_name="default",
    plugin_name: str = "overlay-text",
):
    """Send overlay text via the core overlay subsystem.

    The *plugin_name* parameter is kept for backward compatibility but
    is no longer used — overlay is a core subsystem, not a plugin.
    """
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = OverlayManager()
    return _manager.dispatch(title, subtitle, duration, overlay_name)
