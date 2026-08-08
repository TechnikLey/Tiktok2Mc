"""Shared overlay base: config loading and circuit breaker.

Used by both the API-side overlay subsystem (overlay.py) and the
Bridge-side HTTP client (overlay_utils.py).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ruamel.yaml.error import YAMLError

from core.paths import get_config_file
from core.yaml_utils import load_yaml

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
#  Config helper (global config.yaml)
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
#  Manager base (shared config + client init)
# ---------------------------------------------------------------------------


class OverlayManagerBase:
    """Shared overlay manager base: config + circuit-breaker clients."""

    def __init__(self) -> None:
        self.clients: dict[str, OverlayClient] = {}
        self._init_clients()

    def _load_config(self) -> dict[str, Any]:
        """Load and merge overlay config with defaults."""
        cfg = _load_overlay_config()
        merged = DEFAULT_OVERLAY_CONFIG.copy()
        merged.update(cfg)
        return merged

    def _init_clients(self) -> None:
        cfg = self._load_config()
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
        self._init_clients()

    def get_client(self, name: str) -> OverlayClient | None:
        return self.clients.get(name)

    def check_cooldown(self, name: str) -> tuple[bool, int]:
        client = self.clients.get(name)
        if not client:
            return True, 0
        return client.get_cooldown_status()

    def mark_success(self, name: str) -> None:
        client = self.clients.get(name)
        if client:
            client.mark_success()

    def mark_failure(self, name: str) -> None:
        client = self.clients.get(name)
        if client:
            client.mark_failure()
