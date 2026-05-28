"""API-only plugin discovery.

The launcher fetches the plugin list from the central API
(``GET /api/v1/plugins``).  If the API is unreachable the
launcher returns an empty list — there is no legacy file fallback.

Usage
-----
    from core.api.launcher import PluginLauncher

    launcher = PluginLauncher()
    plugins = launcher.get_plugins()

    print(launcher.source)      # "api" or "empty"
    print(launcher.using_api)   # True when API responded
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from core.models import AppConfig

log = logging.getLogger(__name__)

_API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:29185/api/v1")
_TIMEOUT = 5


# ── field mapping ────────────────────────────────────────────────────


def _api_to_legacy_dict(api_entry: dict[str, Any]) -> dict[str, Any]:
    """Map API ``PluginRegistration`` keys to the dict format expected
    by ``AppConfig``.

    +------------------+------------------+
    | API (new)        | Legacy (old)     |
    +------------------+------------------+
    | ``name``         | ``name``         |
    | ``path``         | ``path``         |
    | ``enabled``      | ``enable``       |
    | ``level``        | ``level``        |
    | ``ics``          | ``ics``          |
    | ``port``         | ``port``         |
    +------------------+------------------+
    """
    return {
        "name": api_entry.get("name", ""),
        "path": api_entry.get("path", ""),
        "enable": api_entry.get("enabled", False),
        "level": api_entry.get("level", 2),
        "ics": api_entry.get("ics", False),
        "port": api_entry.get("port", 0),
    }


# ── launcher ─────────────────────────────────────────────────────────


class PluginLauncher:
    """Reads the plugin list from the central API.

    There is **no** legacy file fallback.  If the API is unreachable
    the launcher returns an empty list.

    Attributes
    ----------
    source : str
        ``"api"`` when the API responded, ``"empty"`` otherwise.
    plugin_count : int
        Number of plugins returned by the last ``get_plugins()`` call.
    """

    def __init__(self, api_base_url: str | None = None) -> None:
        self._api_base = (api_base_url or _API_BASE).rstrip("/")
        self.source: str = "empty"
        self.plugin_count: int = 0

    @property
    def using_api(self) -> bool:
        return self.source == "api"

    def get_plugins(self) -> list[AppConfig]:
        """Fetch plugins from ``GET /api/v1/plugins``.

        Returns an empty list when the API is unreachable.
        """
        plugins = self._fetch()
        if plugins is not None:
            self.source = "api"
            self.plugin_count = len(plugins)
            if plugins:
                log.info(
                    "Plugin source: API (%d plugin(s))",
                    self.plugin_count,
                )
            else:
                log.info("Plugin source: API — 0 plugins registered")
            return plugins

        self.source = "empty"
        self.plugin_count = 0
        log.warning(
            "Plugin source: API unreachable — no plugins loaded"
        )
        return []

    # -- internals ----------------------------------------------------------

    def _fetch(self) -> list[AppConfig] | None:
        """``GET /api/v1/plugins``.  Returns ``None`` on error."""
        url = f"{self._api_base}/plugins"
        try:
            with urllib.request.urlopen(url, timeout=_TIMEOUT) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError,
                ConnectionResetError, TimeoutError, OSError,
                json.JSONDecodeError, ValueError) as exc:
            log.debug("API GET /plugins failed: %s", exc)
            return None

        plugins_raw = raw.get("plugins") or []
        result: list[AppConfig] = []
        for entry in plugins_raw:
            try:
                result.append(
                    AppConfig.from_dict(_api_to_legacy_dict(entry))
                )
            except Exception as exc:
                log.warning(
                    "Skipping invalid API entry %s: %s",
                    entry.get("name", "<unknown>"), exc,
                )
        return result
