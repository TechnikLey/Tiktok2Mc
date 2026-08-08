"""Manifest-driven plugin discovery.

The launcher discovers plugins by reading ``plugin.json`` manifest files
from the plugins directory.  Each valid manifest is registered with the
central API via ``POST /api/v1/plugins/register``, then the launcher
fetches the complete list from ``GET /api/v1/plugins``.

There is **no** file-scanning fallback.  If no manifests exist the
plugin list is empty.  If the API is unreachable, discovery is deferred
and an empty list is returned.

Usage
-----
    from core.api.launcher import PluginLauncher

    launcher = PluginLauncher()
    plugins = launcher.get_plugins()
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from core.api.dependency import get_dependency_order
from core.api.models import PluginManifest, PluginRegistration
from core.models import AppConfig

log = logging.getLogger(__name__)

_TIMEOUT = 5


def _get_api_base() -> str:
    """Return the API base URL, checking the environment on every call."""
    return os.environ.get("API_BASE_URL", "http://127.0.0.1:29185/api/v1")
_PLUGINS_DIR_NAME = "plugins"


# ── field mapping ────────────────────────────────────────────────────


def _api_to_legacy_dict(api_entry: dict[str, Any]) -> dict[str, Any]:
    """Map API ``PluginRegistration`` keys to the dict format expected
    by ``AppConfig``."""
    return {
        "name": api_entry.get("name", ""),
        "path": api_entry.get("path", ""),
        "enable": api_entry.get("enabled", False),
        "level": api_entry.get("level", 2),
        "ics": api_entry.get("ics", False),
        "depends_on": api_entry.get("depends_on", []),
    }


# ── launcher ─────────────────────────────────────────────────────────


class PluginLauncher:
    """Discovers plugins from ``plugin.json`` manifests and registers
    them with the central API.

    Attributes
    ----------
    source : str
        ``"manifest"`` when manifests were found and registered,
        ``"api"`` when the existing API registration was used,
        ``"empty"`` otherwise.
    plugin_count : int
        Number of plugins returned by the last ``get_plugins()`` call.
    """

    def __init__(
        self,
        api_base_url: str | None = None,
        plugins_dir: Path | None = None,
    ) -> None:
        self._api_base = (api_base_url or _get_api_base()).rstrip("/")
        self._plugins_dir: Path | None = plugins_dir
        self.source: str = "empty"
        self.plugin_count: int = 0

    @property
    def using_api(self) -> bool:
        return self.source in ("manifest", "api")

    def get_plugins(self) -> list[AppConfig]:
        """Discover plugins from manifests and return the full list.

        1. Read ``plugin.json`` manifests from the plugins directory.
        2. Register each valid manifest with the central API.
        3. Fetch the complete plugin list from the API.

        Returns an empty list when no manifests exist or the API is
        unreachable.
        """
        # Step 1 — discover from manifests
        manifests = self._discover_from_manifests()
        if manifests:
            self._register_manifests(manifests)

        # Step 2 — fetch from API
        plugins = self._fetch()
        if plugins is not None:
            self.source = "manifest" if manifests else "api"
            self.plugin_count = len(plugins)
            if plugins:
                log.info(
                    "Plugin source: %s (%d plugin(s))",
                    self.source, self.plugin_count,
                )
            else:
                log.info("Plugin source: %s — 0 plugins registered", self.source)
            return plugins

        self.source = "empty"
        self.plugin_count = 0
        log.warning(
            "Plugin source: API unreachable — no plugins loaded"
        )
        return []

    # -- manifest discovery ------------------------------------------------

    def _plugins_directory(self) -> Path | None:
        """Return the resolved plugins directory path, or None."""
        if self._plugins_dir is not None:
            return self._plugins_dir
        try:
            from core.paths import get_root_dir
            root = get_root_dir()
            # Dev layout: src/plugins/   Release layout: plugins/
            dev_dir = root / "src" / _PLUGINS_DIR_NAME
            if dev_dir.is_dir():
                return dev_dir
            rel_dir = root / _PLUGINS_DIR_NAME
            if rel_dir.is_dir():
                return rel_dir
            return None
        except (ImportError, OSError):
            return None

    def _discover_from_manifests(self) -> list[PluginManifest]:
        """Scan the plugins directory for ``plugin.json`` files.

        Returns a list of validated ``PluginManifest`` objects.
        Invalid manifests are logged as warnings and skipped.
        """
        plugins_dir = self._plugins_directory()
        if plugins_dir is None or not plugins_dir.is_dir():
            return []

        results: list[PluginManifest] = []
        seen_names: set[str] = set()

        for child in sorted(plugins_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest_file = child / "plugin.json"
            if not manifest_file.is_file():
                continue

            try:
                with manifest_file.open("r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                manifest = PluginManifest(**raw)
            except (json.JSONDecodeError, ValueError) as exc:
                log.warning(
                    "Skipping invalid manifest %s: %s",
                    manifest_file, exc,
                )
                continue

            if manifest.name in seen_names:
                log.warning(
                    "Duplicate plugin name '%s' in %s — skipping",
                    manifest.name, manifest_file,
                )
                continue
            seen_names.add(manifest.name)
            results.append(manifest)

        return results

    def _register_manifests(
        self, manifests: list[PluginManifest]
    ) -> None:
        """Register each manifest with the central API.

        In release builds (frozen executables) the entry_point path
        is normalised: the ``src/`` prefix is stripped and ``.py``
        is replaced by the platform executable suffix so the
        launcher points to the compiled binary.
        """
        import sys

        from core.paths import get_root_dir

        root = get_root_dir()
        frozen = getattr(sys, "frozen", False)
        suffix = ".exe" if sys.platform == "win32" else ".bin"

        for manifest in manifests:
            entry_point = manifest.entry_point or ""
            if frozen:
                # Normalise dev path → release executable path
                entry_point = entry_point.replace("\\", "/")
                if entry_point.startswith("src/"):
                    entry_point = entry_point[len("src/"):]
                if entry_point.endswith(".py"):
                    entry_point = entry_point[: -len(".py")] + suffix

            entry_path = root / entry_point if entry_point else ""

            # Sanity check: if the resolved path does not exist and we are
            # in frozen mode, log a warning so the user knows the build may
            # be incomplete.
            if frozen and entry_path and not entry_path.exists():
                log.warning(
                    "Plugin executable not found: %s (did the release build copy it?)",
                    entry_path,
                )

            registration = PluginRegistration.from_manifest(
                manifest,
                path=str(entry_path),
                enabled=False,
            )
            self._register(registration)

    def _register(self, plugin: PluginRegistration) -> bool:
        """``POST /api/v1/plugins/register``.  Returns ``True`` on success."""
        url = f"{self._api_base}/plugins/register"
        body = plugin.model_dump(mode="json")
        data = json.dumps(body).encode("utf-8")
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT):
                log.debug("Registered plugin: %s", plugin.name)
                return True
        except (urllib.error.URLError, OSError) as exc:
            log.warning("Failed to register plugin '%s': %s", plugin.name, exc)
            return False

    # -- API fetch ---------------------------------------------------------

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
            except (ValueError, TypeError) as exc:
                log.warning(
                    "Skipping invalid API entry %s: %s",
                    entry.get("name", "<unknown>"), exc,
                )
        # Sort by dependency order so dependants start after dependencies
        result = [
            AppConfig.from_dict(d)
            for d in get_dependency_order(
                [p.to_dict() for p in result],
            )
        ]
        return result
