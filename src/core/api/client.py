"""HTTP client for the central API plugin registry.

Plugins register themselves via ``register_plugin()`` which sends
a ``POST /api/v1/plugins/register`` to the central API.
There is no legacy file fallback — the API is the only registry.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.models import AppConfig

log = logging.getLogger(__name__)

_API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:29185/api/v1")
_TIMEOUT = 5


# ── helpers ──────────────────────────────────────────────────────────


def _map_to_api_body(config: AppConfig | dict[str, Any]) -> dict[str, Any]:
    """Normalise an ``AppConfig`` / dict to the API schema."""
    if isinstance(config, AppConfig):
        d = config.to_dict()
    else:
        d = dict(config)

    if "enable" in d and "enabled" not in d:
        d["enabled"] = d.pop("enable")
    if "path" in d:
        d["path"] = str(d["path"])
    d.setdefault("version", "1.0.0")
    d.setdefault("description", "")
    return d


def _api_to_app_config(data: dict[str, Any]) -> AppConfig:
    """Convert an API response body back to ``AppConfig``."""
    return AppConfig(
        name=data["name"],
        path=Path(data.get("path", "")),
        enable=data.get("enabled", False),
        level=data.get("level", 2),
        ics=data.get("ics", False),
    )


# ── class-based client ───────────────────────────────────────────────


class PluginAPIClient:
    """HTTP wrapper around plugin registry endpoints."""

    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or _API_BASE).rstrip("/")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def register(self, body: dict[str, Any]) -> dict[str, Any] | None:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self._url("plugins/register"), data=data,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                if resp.status in (200, 201):
                    return json.loads(resp.read().decode("utf-8")).get("plugin")
                return None
        except (urllib.error.URLError, urllib.error.HTTPError,
                ConnectionResetError, TimeoutError, OSError):
            return None

    def unregister(self, name: str) -> bool:
        req = urllib.request.Request(
            self._url(f"plugins/{urllib.request.quote(name, safe='')}"),
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT):
                return True
        except (urllib.error.URLError, urllib.error.HTTPError,
                ConnectionResetError, TimeoutError, OSError):
            return False

    def get(self, name: str) -> dict[str, Any] | None:
        req = urllib.request.Request(
            self._url(f"plugins/{urllib.request.quote(name, safe='')}"),
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
                return None
        except (urllib.error.URLError, urllib.error.HTTPError,
                ConnectionResetError, TimeoutError, OSError):
            return None

    def update(self, name: str, body: dict[str, Any]) -> dict[str, Any] | None:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self._url(f"plugins/{urllib.request.quote(name, safe='')}"),
            data=data,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
                return None
        except (urllib.error.URLError, urllib.error.HTTPError,
                ConnectionResetError, TimeoutError, OSError):
            return None

    def list(self) -> list[dict[str, Any]]:
        req = urllib.request.Request(self._url("plugins"), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("plugins", [])
        except (urllib.error.URLError, urllib.error.HTTPError,
                ConnectionResetError, TimeoutError, OSError):
            return []


# ── module-level convenience  ────────────────────────────────────────

_client: PluginAPIClient | None = None


def _get_client() -> PluginAPIClient:
    global _client
    if _client is None:
        _client = PluginAPIClient()
    return _client


def register_plugin(config: AppConfig | dict[str, Any]) -> AppConfig:
    """Register a plugin with the central API.

    Accepts the same types as the old ``python.registry.register_plugin()``
    did (``AppConfig`` or ``dict``) and returns an ``AppConfig``.

    Raises ``ConnectionError`` if the API is unreachable.
    """
    body = _map_to_api_body(config)
    result = _get_client().register(body)

    if result is None:
        raise ConnectionError(
            f"Cannot register '{body.get('name')}': "
            f"API at {_API_BASE} unreachable or returned an error"
        )

    log.info(
        "Registered via API: %s (enabled=%s)",
        result.get("name"), result.get("enabled"),
    )
    return _api_to_app_config(result)
