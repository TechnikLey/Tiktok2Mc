"""API-managed plugin registry — single source of truth.

Replaces the old file-based ``PLUGIN_REGISTRY.json`` that was written
by ``python.registry.register_plugin()``.  The new registry lives in
``data/api_plugin_registry.json`` and is served, validated, and
persisted entirely by the API layer.
"""

from __future__ import annotations

import json
import time
import threading
import logging
from pathlib import Path
from typing import Any

from core.api.models import PluginRegistration

log = logging.getLogger(__name__)

STORAGE_FILENAME = "api_plugin_registry.json"


class PluginRegistry:
    """Thread-safe, file-persisted plugin registry.

    This is the **canonical** registry for Phase 3+.  Old code that
    writes to ``PLUGIN_REGISTRY.json`` can still coexist — use
    :meth:`import_legacy` to absorb its data.
    """

    def __init__(self, storage_dir: Path) -> None:
        self._file: Path = (storage_dir / STORAGE_FILENAME).resolve()
        self._plugins: dict[str, PluginRegistration] = {}
        self._lock = threading.Lock()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, data: PluginRegistration) -> PluginRegistration:
        """Insert or update a plugin entry."""
        now = time.time()
        data.registered_at = data.registered_at or now
        data.updated_at = now
        with self._lock:
            self._plugins[data.name] = data
            self._save()
        return data

    def unregister(self, name: str) -> bool:
        """Remove a plugin by name.  Returns ``True`` if it existed."""
        with self._lock:
            if name in self._plugins:
                del self._plugins[name]
                self._save()
                return True
        return False

    def get(self, name: str) -> PluginRegistration | None:
        with self._lock:
            return self._plugins.get(name)

    def list(self) -> list[PluginRegistration]:
        with self._lock:
            return list(self._plugins.values())

    def update(
        self, name: str, **updates: Any
    ) -> PluginRegistration | None:
        """Partial update of a plugin entry.

        Only the supplied keyword arguments are changed; everything
        else is preserved.
        """
        with self._lock:
            plugin = self._plugins.get(name)
            if plugin is None:
                return None
            changed = False
            for key, value in updates.items():
                if value is not None and hasattr(plugin, key):
                    old = getattr(plugin, key)
                    if old != value:
                        setattr(plugin, key, value)
                        changed = True
            if changed:
                plugin.updated_at = time.time()
                self._save()
            return plugin

    # ------------------------------------------------------------------
    # Legacy import
    # ------------------------------------------------------------------

    def import_legacy(self, items: list[dict[str, Any]]) -> int:
        """Bulk-import plugins from the old ``PLUGIN_REGISTRY.json``
        format.  Returns the number of imported entries."""
        now = time.time()
        count = 0
        with self._lock:
            for item in items:
                name = item.get("name")
                if not name:
                    continue
                existing = self._plugins.get(name)
                entry = PluginRegistration(
                    name=name,
                    path=str(item.get("path", "")),
                    version=item.get("version", "1.0.0"),
                    enabled=bool(
                        item.get("enable", item.get("enabled", False))
                    ),
                    level=int(item.get("level", 2)),
                    port=int(item.get("port", 0)),
                    ics=bool(item.get("ics", False)),
                    registered_at=(
                        existing.registered_at if existing else now
                    ),
                    updated_at=now,
                )
                self._plugins[name] = entry
                count += 1
            self._save()
        return count

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            with self._file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            for item in data if isinstance(data, list) else []:
                try:
                    plugin = PluginRegistration(**item)
                    self._plugins[plugin.name] = plugin
                except Exception as exc:
                    log.warning("Skipping invalid registry entry: %s", exc)
        except Exception as exc:
            log.warning("Failed to load plugin registry: %s", exc)

    def _save(self) -> None:
        data = [p.model_dump(mode="json") for p in self._plugins.values()]
        tmp = self._file.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.flush()
            tmp.replace(self._file)
        except Exception as exc:
            log.error("Failed to save plugin registry: %s", exc)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Return the global ``PluginRegistry``, creating it on first call.

    The storage directory is derived from the project root (``data/``).
    """
    global _registry
    if _registry is None:
        from core.paths import get_root_dir

        storage_dir = get_root_dir() / "data"
        storage_dir.mkdir(parents=True, exist_ok=True)
        _registry = PluginRegistry(storage_dir)
    return _registry
