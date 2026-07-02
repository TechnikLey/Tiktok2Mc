"""Centralized backup manager — single source of truth for all backups.
 
 All backups are stored under ``data/backups/``, organized by category::
 
     data/backups/
     ├── config/                 # Main config.yaml backups
     ├── plugin_registry/        # api_plugin_registry.json backups
     ├── migration/              # Pre-migration safety snapshots
     └── plugins/
         └── <plugin_name>/      # Per-plugin config.yaml backups
 
 Features
 --------
 * **Content deduplication** — SHA-256 hash comparison skips identical backups.
 * **Time coalescing** — skips backup if one was created within the last 60 s.
 * **Retention enforcement** — keeps only the *N* newest backups per category
   (default: 10, configurable).
 * **Timestamp-based naming** — lexicographically sortable, human-readable
   filenames (``config.v20260529_143021_123456.yaml.bak``).
 """
 
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

from core.error_codes import BACKUP_0001, BACKUP_0002
from core.crash_manager import get_crash_manager

log = logging.getLogger(__name__)

# ── defaults ──────────────────────────────────────────────────────────

BACKUP_ROOT_RELATIVE = "data/backups"
DEFAULT_MAX_BACKUPS = 10
DEFAULT_COALESCE_SECONDS = 60


def _read_hash(path: Path) -> str:
    """Return the SHA-256 hex digest of *path*."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(65536)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _timestamp_tag() -> str:
    """Return a sortable, human-readable timestamp tag."""
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


class BackupManager:
    """Centralized backup manager.

    Parameters
    ----------
    root_dir:
        Project root directory.  Backups are stored at
        ``root_dir / data/backups/``.
    max_backups:
        Maximum number of backups to retain per category after each
        ``create_backup`` call.
    coalesce_seconds:
        Skip creating a backup if the most recent backup in the same
        category is younger than this many seconds.
    """

    def __init__(
        self,
        root_dir: Path | None = None,
        max_backups: int = DEFAULT_MAX_BACKUPS,
        coalesce_seconds: int = DEFAULT_COALESCE_SECONDS,
    ) -> None:
        if root_dir is None:
            from core.paths import get_root_dir

            root_dir = get_root_dir()
        self._root = root_dir.resolve()
        self._backup_root = self._root / BACKUP_ROOT_RELATIVE
        self.max_backups = max_backups
        self.coalesce_seconds = coalesce_seconds

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_backup(
        self,
        source_path: Path,
        category: str | None = None,
    ) -> Path | None:
        """Create a backup of *source_path*.

        Returns the backup ``Path``, or ``None`` if the backup was
        skipped (identical content, too soon since last backup, or
        *source_path* does not exist).

        When *category* is ``None`` it is inferred from the path:
        * ``config/.../config.yaml`` → ``"config"``
        * ``.../plugins/<name>/...`` → ``"plugins/<name>"``
        * ``api_plugin_registry.json`` → ``"plugin_registry"``
        * anything else → ``"_other"``
        """
        source = source_path.resolve()
        if not source.exists():
            return None

        cat = category or self._default_category(source)
        backup_dir = self._backup_root / cat
        backup_dir.mkdir(parents=True, exist_ok=True)

        # ── deduplication: content hash ──────────────────────────────
        current_hash = _read_hash(source)
        existing = sorted(backup_dir.iterdir()) if backup_dir.exists() else []
        if existing:
            last = existing[-1]
            try:
                if _read_hash(last) == current_hash:
                    log.debug(
                        "Backup skipped — content unchanged: %s", source
                    )
                    return None
            except Exception:
                pass

        # ── time coalescing ──────────────────────────────────────────
        if existing:
            last_mtime = existing[-1].stat().st_mtime
            if time.time() - last_mtime < self.coalesce_seconds:
                log.debug(
                    "Backup skipped — too soon since last backup: %s",
                    source,
                )
                return None

        # ── create backup ────────────────────────────────────────────
        stem = source.stem
        suffix = source.suffix
        tag = _timestamp_tag()
        bak_name = f"{stem}.v{tag}{suffix}.bak"
        bak_path = backup_dir / bak_name

        shutil.copy2(source, bak_path)
        log.info("Backup created: %s", bak_path)

        # ── enforce retention ────────────────────────────────────────
        self._enforce_retention(cat)

        return bak_path

    def list_backups(
        self, category: str, max_count: int = 0
    ) -> list[Path]:
        """Return backup paths in *category*, newest first.

        If *max_count* > 0 the list is truncated to the latest entries.
        """
        backup_dir = self._backup_root / category
        if not backup_dir.exists():
            return []
        files = sorted(backup_dir.iterdir(), reverse=True)
        if max_count > 0:
            files = files[:max_count]
        return files

    def restore_backup(
        self, backup_path: Path, target_path: Path
    ) -> None:
        """Restore *backup_path* to *target_path* (replaces target)."""
        shutil.copy2(backup_path, target_path)
        log.info("Restored %s → %s", backup_path, target_path)

    def cleanup(
        self, category: str | None = None, max_backups: int | None = None
    ) -> int:
        """Remove excess backups, keeping the *max_backups* newest.

        Returns the number of files removed.  When *category* is
        ``None`` every subdirectory under the backup root is cleaned.
        """
        max_b = max_backups if max_backups is not None else self.max_backups
        removed = 0
        if category is not None:
            return self._enforce_retention(category, max_b)
        for child in sorted(self._backup_root.iterdir()):
            if child.is_dir():
                removed += self._enforce_retention(
                    child.name, max_b
                )
        return removed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enforce_retention(
        self, category: str, max_backups: int | None = None
    ) -> int:
        """Keep the *max_backups* newest backups in *category*.

        Returns the count of files removed.
        """
        max_b = max_backups if max_backups is not None else self.max_backups
        backup_dir = self._backup_root / category
        if not backup_dir.exists():
            return 0
        files = sorted(backup_dir.iterdir())
        if len(files) <= max_b:
            return 0
        removed = 0
        for f in files[:-max_b]:
            try:
                f.unlink()
                removed += 1
            except Exception as exc:
                log.warning("Failed to remove old backup %s: %s", f, exc)
        if removed:
            log.info(
                "Cleaned %d old backup(s) from category '%s' (keeping %d)",
                removed,
                category,
                max_b,
            )
        return removed

    @staticmethod
    def _default_category(path: Path) -> str:
        """Infer a category name from *path*."""
        resolved = path.resolve()
        name = resolved.name

        if name == "config.yaml":
            # Walk parents to detect plugin trees
            for parent in resolved.parents:
                if parent.name == "plugins":
                    # parent.parent is the directory containing plugins/
                    # The immediate parent of config.yaml is the plugin dir
                    plugin_name = resolved.parent.name
                    return f"plugins/{plugin_name}"
            return "config"

        if "api_plugin_registry" in name:
            return "plugin_registry"

        return "_other"


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_backup_manager: BackupManager | None = None


def get_backup_manager() -> BackupManager:
    """Return the global ``BackupManager``, creating it on first call."""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager
