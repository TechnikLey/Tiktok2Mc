"""API-managed plugin registry — single source of truth.

The registry lives in ``data/api_plugin_registry.json`` and is served,
validated, and persisted entirely by the API layer.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from core.api.models import PluginRegistration
from core.backup import get_backup_manager

log = logging.getLogger(__name__)

STORAGE_FILENAME = "api_plugin_registry.json"

# Sentinel used to distinguish "explicitly set to None" from "not provided"
# in ``PluginRegistry.update(**updates)``.  ``None`` means "leave unchanged";
# ``_UNSET`` means "clear this field".
_UNSET = object()


class PluginRegistry:
    """Thread-safe, file-persisted plugin registry.

    This is the **canonical** registry — the single source of truth
    for all plugin metadata.  Backups are managed by the centralized
    ``BackupManager`` (``data/backups/plugin_registry/``).
    """

    def __init__(self, storage_dir: Path) -> None:
        """Load the registry from ``storage_dir`` and create a startup backup.

Existing entries are read from ``api_plugin_registry.json``. A single
backup is taken when the file already exists; failures are logged and do
not prevent startup."""

        self._file: Path = (storage_dir / STORAGE_FILENAME).resolve()
        self._plugins: dict[str, PluginRegistration] = {}
        self._lock = threading.Lock()
        self._load()
        # One-time backup on startup (not on every save)
        if self._file.exists():
            try:
                get_backup_manager().create_backup(
                    self._file, category="plugin_registry"
                )
            except OSError as exc:
                log.warning("Failed to create startup registry backup: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, data: PluginRegistration) -> PluginRegistration:
        """Insert or update a plugin entry.

        Preserves the existing ``enabled`` and ``registered_at`` state
        when a plugin is already registered — the launcher must NOT
        override runtime state.
        """
        now = time.time()
        data.registered_at = data.registered_at or now
        data.updated_at = now
        with self._lock:
            existing = self._plugins.get(data.name)
            if existing is not None:
                data.enabled = existing.enabled
                data.registered_at = existing.registered_at
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
        """Return the plugin registered under ``name``, or ``None``.

The returned model is the live registry object, not a copy."""

        with self._lock:
            return self._plugins.get(name)

    def list(self) -> list[PluginRegistration]:
        """Return all registered plugins in registration order.

The list is a snapshot, but its entries are the live registry objects."""

        with self._lock:
            return list(self._plugins.values())

    def update(self, name: str, **updates: Any) -> PluginRegistration | None:
        """Partial update of a plugin entry.

        Only the supplied keyword arguments are changed; everything
        else is preserved.  Pass ``_UNSET`` as the value for a field
        to explicitly set it to ``None``.
        """
        with self._lock:
            plugin = self._plugins.get(name)
            if plugin is None:
                return None
            changed = False
            for key, value in updates.items():
                if value is _UNSET and hasattr(plugin, key):
                    if getattr(plugin, key) is not None:
                        setattr(plugin, key, None)
                        changed = True
                    continue
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
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Populate the in-memory mapping from the registry file.

A missing file leaves the registry empty. Malformed JSON or unreadable
files are logged and ignored; individual invalid entries are skipped while
valid entries are still loaded."""

        if not self._file.exists():
            return
        try:
            with self._file.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            for item in data if isinstance(data, list) else []:
                try:
                    plugin = PluginRegistration(**item)
                    self._plugins[plugin.name] = plugin
                except (ValueError, TypeError) as exc:
                    log.warning("Skipping invalid registry entry: %s", exc)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load plugin registry: %s", exc)

    def _save(self) -> None:
        """Persist the registry atomically.

The JSON is written to a temporary file, flushed to disk, and then moved
over the target. Errors are logged rather than raised, so a failed write
does not break the caller's request."""

        data = [p.model_dump(mode="json") for p in self._plugins.values()]
        tmp = self._file.with_suffix(".json.tmp")
        try:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.flush()
                os.fsync(fh.fileno())
            self._atomic_replace(tmp, self._file)
        except (OSError, TypeError) as exc:
            log.error("Failed to save plugin registry: %s", exc)

    @staticmethod
    def _atomic_replace(src: Path, dst: Path) -> None:
        """Atomically replace *dst* with *src*.

        On Windows, ``os.replace`` cannot overwrite a file that is currently
        open in another process.  We first attempt a normal replace; if that
        fails with a permission error we remove the destination and retry.
        """
        try:
            src.replace(dst)
            return
        except PermissionError:
            if sys.platform != "win32" or not dst.exists():
                raise
        dst.unlink()
        src.replace(dst)


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
