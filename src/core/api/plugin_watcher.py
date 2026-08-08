"""Plugin directory watcher — auto-syncs registry with filesystem state.

Polling-based: compares the current set of plugin manifests on disk
against the registry every N seconds.  New plugins are auto-registered
and removed plugins are auto-unregistered.
"""

import json
import logging
import time
import threading
from pathlib import Path
from typing import Set

from core.api.registry import get_registry
from core.api.models import PluginRegistration
from core.health_monitor import get_health_monitor, HealthState

log = logging.getLogger(__name__)

_POLL_INTERVAL = 10.0


def _get_plugin_dirs(plugins_dir: Path) -> dict[str, Path]:
    """Return ``{name: path}`` for every directory containing a valid
    ``plugin.json`` under *plugins_dir*."""
    result: dict[str, Path] = {}
    if not plugins_dir.is_dir():
        return result
    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir():
            continue
        manifest_file = child / "plugin.json"
        if not manifest_file.is_file():
            continue
        try:
            with manifest_file.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
            name = raw.get("name", "")
            if name and isinstance(name, str):
                result[name] = child
        except (json.JSONDecodeError, OSError):
            continue
    return result


class PluginWatcher:
    """Polling-based watcher that keeps the registry in sync with the
    plugins directory.

    Runs as a daemon thread.  Detects:
    * New plugin directories → auto-register
    * Removed plugin directories → auto-unregister
    """

    def __init__(self, plugins_dir: Path | None = None) -> None:
        self._plugins_dir: Path | None = plugins_dir
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._known: Set[str] = set()
        self._health = get_health_monitor()
        self._health.register("plugin_watcher", HealthState.STARTING)

    def _resolve_plugins_dir(self) -> Path | None:
        if self._plugins_dir is not None:
            return self._plugins_dir
        try:
            from core.paths import get_root_dir
            root = get_root_dir()
            dev_dir = root / "src" / "plugins"
            if dev_dir.is_dir():
                return dev_dir
            rel_dir = root / "plugins"
            if rel_dir.is_dir():
                return rel_dir
            return None
        except (ImportError, OSError):
            return None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        # Snapshot current state
        plugins_dir = self._resolve_plugins_dir()
        if plugins_dir:
            self._known = set(_get_plugin_dirs(plugins_dir).keys())
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._health.set_state("plugin_watcher", HealthState.RUNNING)
        log.info("Plugin watcher started (poll interval: %ss)", _POLL_INTERVAL)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._health.set_state("plugin_watcher", HealthState.STOPPED)
        log.info("Plugin watcher stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._sync()
            self._stop_event.wait(_POLL_INTERVAL)

    def _sync(self) -> None:
        plugins_dir = self._resolve_plugins_dir()
        if plugins_dir is None:
            return

        try:
            current = _get_plugin_dirs(plugins_dir)
            current_names: Set[str] = set(current.keys())
            registry = get_registry()

            # New plugins on disk not in registry → auto-register
            for name in current_names - self._known:
                plugin_dir = current[name]
                try:
                    with (plugin_dir / "plugin.json").open("r", encoding="utf-8") as fh:
                        raw = json.load(fh)
                    entry_point = raw.get("entry_point", "")
                    manifest_path_part = raw.get("entry_point", "")
                    registration = PluginRegistration(
                        name=name,
                        path=str(plugin_dir / entry_point) if entry_point else str(plugin_dir),
                        entry_point=manifest_path_part,
                        display_name=raw.get("display_name", name),
                        version=raw.get("version", "0.0.0"),
                        enabled=False,
                        description=raw.get("description", ""),
                        update_url=raw.get("update_url", ""),
                    )
                    registry.register(registration)
                    log.info("Auto-registered new plugin: '%s'", name)
                except (json.JSONDecodeError, OSError, ValueError) as exc:
                    log.warning("Failed to auto-register plugin '%s': %s", name, exc)

            # Plugins in registry but gone from disk → auto-unregister
            reg_names: Set[str] = {p.name for p in registry.list()}
            gone = reg_names - current_names
            for name in gone:
                if name in self._known:
                    registry.unregister(name)
                    log.info("Auto-unregistered removed plugin: '%s'", name)

            self._known = current_names

        except (OSError, ValueError) as exc:
            log.debug("Plugin watcher sync error: %s", exc)


_plugin_watcher: PluginWatcher | None = None


def get_plugin_watcher() -> PluginWatcher:
    global _plugin_watcher
    if _plugin_watcher is None:
        _plugin_watcher = PluginWatcher()
    return _plugin_watcher
