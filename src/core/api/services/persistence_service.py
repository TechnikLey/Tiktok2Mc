"""Namespaced key-value persistence for plugins and hooks.

Every extension (plugin or hook) gets its own JSON file under
``data/plugin_data/<namespace>.json`` so extensions no longer have to share
the global ``data/`` directory.  Values are arbitrary JSON-serializable
data; writes are atomic (temp file + replace) and guarded by a lock.

Access from extensions:
- Plugins: HTTP endpoints ``/api/v1/plugins/{name}/data[/{key}]`` or the
  ``store_*`` helpers on :class:`core.base_plugin.BasePlugin`.
- Hooks: the same HTTP endpoints (hooks run inside the bridge process and
  therefore talk to the API over HTTP like any other client).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

from core.paths import get_plugin_data_dir

log = logging.getLogger(__name__)

_NAMESPACE_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_KEY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class PersistenceError(ValueError):
    """Raised for invalid namespaces or keys."""


class PersistenceService:
    """File-backed, namespaced JSON store.

    One ``<namespace>.json`` file per plugin/hook inside the plugin data
    directory.  All mutating operations are atomic and thread-safe.
    """

    def __init__(self, storage_dir: Path | None = None) -> None:
        self._storage_dir = storage_dir or get_plugin_data_dir()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def validate_namespace(namespace: str) -> str:
        if not isinstance(namespace, str) or not _NAMESPACE_RE.match(namespace):
            raise PersistenceError(
                f"Namespace must match [A-Za-z0-9_-]{{1,64}} (got: {namespace!r})"
            )
        return namespace

    @staticmethod
    def validate_key(key: str) -> str:
        if not isinstance(key, str) or not _KEY_RE.match(key):
            raise PersistenceError(
                f"Key must match [A-Za-z0-9_.-]{{1,128}} (got: {key!r})"
            )
        return key

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_store(self, namespace: str) -> dict[str, Any]:
        """Return all key/value pairs of a namespace (empty dict if absent)."""
        self.validate_namespace(namespace)
        with self._lock:
            return self._read(namespace)

    def get(self, namespace: str, key: str) -> tuple[bool, Any]:
        """Return ``(found, value)`` for a single key."""
        self.validate_key(key)
        store = self.get_store(namespace)
        if key not in store:
            return False, None
        return True, store[key]

    def set(self, namespace: str, key: str, value: Any) -> None:
        """Set ``key`` to ``value`` and persist atomically."""
        self.validate_namespace(namespace)
        self.validate_key(key)
        with self._lock:
            store = self._read(namespace)
            store[key] = value
            self._write(namespace, store)

    def delete(self, namespace: str, key: str) -> bool:
        """Delete ``key``; returns ``False`` when it did not exist."""
        self.validate_key(key)
        self.validate_namespace(namespace)
        with self._lock:
            store = self._read(namespace)
            if key not in store:
                return False
            del store[key]
            self._write(namespace, store)
            return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _file_for(self, namespace: str) -> Path:
        return self._storage_dir / f"{namespace}.json"

    def _read(self, namespace: str) -> dict[str, Any]:
        path = self._file_for(namespace)
        if not path.is_file():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Persistence: failed to read %s: %s", path, exc)
            return {}

    def _write(self, namespace: str, store: dict[str, Any]) -> None:
        path = self._file_for(namespace)
        try:
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except (OSError, TypeError) as exc:
            log.error("Persistence: failed to write %s: %s", path, exc)
            raise PersistenceError(f"Failed to persist '{namespace}': {exc}") from exc


# Singleton
_persistence_service: PersistenceService | None = None


def get_persistence_service() -> PersistenceService:
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = PersistenceService()
    return _persistence_service
