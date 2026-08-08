"""Persistent hook registry — mirrors ``PluginRegistry`` for the hook system.

The registry lives in ``data/hook_registry.json`` and tracks installed hooks,
their versions, enable state, and metadata.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from core.backup import get_backup_manager

log = logging.getLogger(__name__)

STORAGE_FILENAME = "hook_registry.json"


class HookRegistration:
    """Canonical hook record stored in the registry.

    Mirrors ``PluginRegistration`` but simpler — hooks don't have
    separate processes, health monitoring, or heartbeat tracking.
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        enabled: bool = True,
        display_name: str = "",
        description: str = "",
        author: str = "",
        capabilities: list[str] | None = None,
        plugin: str = "",
        update_url: str = "",
        source: str = "",
        error: str = "",
        registered_at: float | None = None,
        updated_at: float | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.enabled = enabled
        self.display_name = display_name
        self.description = description
        self.author = author
        self.capabilities = capabilities or []
        self.plugin = plugin
        self.update_url = update_url
        self.source = source
        self.error = error
        self.registered_at = registered_at or time.time()
        self.updated_at = updated_at or time.time()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "enabled": self.enabled,
            "display_name": self.display_name,
            "description": self.description,
            "author": self.author,
            "capabilities": self.capabilities,
            "plugin": self.plugin,
            "update_url": self.update_url,
            "source": self.source,
            "error": self.error,
            "registered_at": self.registered_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HookRegistration:
        return cls(**data)


class HookRegistry:
    """Thread-safe, file-persisted hook registry.

    Tracks all known hooks, their versions, and enable state.
    Backups managed by the centralized ``BackupManager``.
    """

    def __init__(self, storage_dir: Path) -> None:
        self._file: Path = (storage_dir / STORAGE_FILENAME).resolve()
        self._hooks: dict[str, HookRegistration] = {}
        self._lock = threading.Lock()
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, data: HookRegistration) -> HookRegistration:
        """Insert or update a hook entry.

        Preserves existing ``enabled`` and ``registered_at`` state
        when a hook is already registered.
        """
        with self._lock:
            existing = self._hooks.get(data.name)
            if existing is not None:
                data.enabled = existing.enabled
                data.registered_at = existing.registered_at
            data.updated_at = time.time()
            self._hooks[data.name] = data
            self._save()
        return data

    def unregister(self, name: str) -> bool:
        """Remove a hook by name. Returns ``True`` if it existed."""
        with self._lock:
            if name in self._hooks:
                del self._hooks[name]
                self._save()
                return True
        return False

    def get(self, name: str) -> HookRegistration | None:
        with self._lock:
            return self._hooks.get(name)

    def list(self) -> list[HookRegistration]:
        with self._lock:
            return list(self._hooks.values())

    def update(self, name: str, **updates: Any) -> HookRegistration | None:
        """Partial update of a hook entry."""
        with self._lock:
            hook = self._hooks.get(name)
            if hook is None:
                return None
            changed = False
            for key, value in updates.items():
                if value is not None and hasattr(hook, key):
                    old = getattr(hook, key)
                    if old != value:
                        setattr(hook, key, value)
                        changed = True
            if changed:
                hook.updated_at = time.time()
                self._save()
            return hook

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Enable or disable a hook. Returns ``True`` on success."""
        return self.update(name, enabled=enabled) is not None

    def is_enabled(self, name: str) -> bool:
        """Check if a hook is enabled (defaults to ``True`` if unknown)."""
        hook = self.get(name)
        return hook.enabled if hook else True

    # ------------------------------------------------------------------
    # Discovery helpers
    # ------------------------------------------------------------------

    def sync_from_discovery(self, discovered: list[dict]) -> int:
        """Sync registry with discovered hooks.

        * Adds new hooks (enabled by default).
        * Updates version/source info for existing hooks.
        * Does **not** remove hooks — use ``stale`` check for that.
        * Includes error info for hooks with broken manifests.

        Returns the number of new registrations.
        """
        count = 0
        for info in discovered:
            existing = self.get(info["name"])
            error = info.get("_error", info.get("error", ""))
            if existing is None:
                reg_info = {k: v for k, v in info.items() if k != "_error"}
                reg_info["error"] = error
                self.register(HookRegistration(**reg_info))
                count += 1
            elif (
                existing.version != info.get("version", existing.version)
                or error != existing.error
            ):
                self.update(
                    info["name"],
                    version=info.get("version", existing.version),
                    source=info.get("source", existing.source),
                    display_name=info.get("display_name", existing.display_name),
                    description=info.get("description", existing.description),
                    error=error,
                )
        return count

    def get_stale(self, active_names: set[str]) -> list[str]:
        """Return names of hooks in the registry that are no longer on disk."""
        return [n for n in self._hooks if n not in active_names]

    def clean_stale(self, active_names: set[str]) -> int:
        """Remove registry entries for hooks no longer on disk.

        Returns the number of removed entries.
        """
        stale = self.get_stale(active_names)
        for name in stale:
            self.unregister(name)
        return len(stale)

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
                    hook = HookRegistration.from_dict(item)
                    self._hooks[hook.name] = hook
                except (ValueError, TypeError) as exc:
                    log.warning("Skipping invalid hook registry entry: %s", exc)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load hook registry: %s", exc)

    def _save(self) -> None:
        data = [h.to_dict() for h in self._hooks.values()]
        tmp = self._file.with_suffix(".json.tmp")
        try:
            if self._file.exists():
                try:
                    get_backup_manager().create_backup(
                        self._file, category="hook_registry"
                    )
                except OSError as exc:
                    log.warning("Failed to create hook registry backup: %s", exc)

            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
                fh.flush()
            tmp.replace(self._file)
        except (OSError, TypeError) as exc:
            log.error("Failed to save hook registry: %s", exc)


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_registry: HookRegistry | None = None


def get_hook_registry() -> HookRegistry:
    """Return the global ``HookRegistry``, creating it on first call.

    Storage directory is derived from the project root (``data/``).
    """
    global _registry
    if _registry is None:
        from core.paths import get_root_dir

        storage_dir = get_root_dir() / "data"
        storage_dir.mkdir(parents=True, exist_ok=True)
        _registry = HookRegistry(storage_dir)
    return _registry
