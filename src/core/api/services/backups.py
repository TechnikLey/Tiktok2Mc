"""BackupService — API-facing facade over the centralized ``BackupManager``.

Bridges the raw backup files under ``data/backups/`` to the GUI:

* ``list_backups`` — enumerate categories and entries with timestamps,
  sizes, and restorability.
* ``restore`` — copy a backup back to its target file (with a safety
  snapshot of the current state first).
* ``create_now`` — trigger backups of known targets on demand.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import core.paths
from core.backup import get_backup_manager

log = logging.getLogger(__name__)

# Matches the version tag inside backup file names:
#   config.v20260529_143021_123456.yaml.bak
_TIMESTAMP_RE = re.compile(r"\.v(\d{8})_(\d{6})_(\d{6})")


def _fixed_target(category: str) -> Path | None:
    """Return the fixed restore target for *category*, if any."""
    if category in ("config", "migration"):
        return core.paths.get_config_file()
    if category == "plugin_registry":
        return core.paths.get_root_dir() / "data" / "api_plugin_registry.json"
    return None


def _actions_path() -> Path:
    from core.api.services.actions import ActionsService

    return ActionsService().actions_path


class BackupService:
    """High-level backup operations for the API layer."""

    @property
    def _manager(self):
        # Resolve lazily so path patching (tests, runtime root) always
        # picks up the current project root.
        return get_backup_manager()

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_backups(self) -> dict[str, Any]:
        """Return backup categories with their entries, newest first."""
        root = self._manager.backup_root
        categories: list[dict[str, Any]] = []
        if not root.is_dir():
            return {"root": str(root), "categories": categories, "total": 0}

        for child in sorted(root.iterdir()):
            if child.is_dir() and child.name == "plugins":
                # Per-plugin backups live one level deeper: plugins/<name>/...
                for sub in sorted(child.iterdir()):
                    if sub.is_dir():
                        self._collect_category(f"plugins/{sub.name}", categories)
            elif child.is_dir():
                self._collect_category(child.name, categories)

        return {
            "root": str(root),
            "categories": categories,
            "total": sum(c["count"] for c in categories),
        }

    def _collect_category(
        self, category: str, categories: list[dict[str, Any]]
    ) -> None:
        """Append *category* to *categories* if it contains any backups."""
        child = self._manager.backup_root / category
        restorable = self._restore_target(category) is not None
        entries = [
            self._entry(category, f, restorable)
            for f in sorted(child.iterdir(), reverse=True)
            if f.is_file()
        ]
        if not entries:
            return
        categories.append(
            {
                "category": category,
                "label": category,
                "count": len(entries),
                "entries": entries,
            }
        )

    @staticmethod
    def _entry(category: str, path: Path, restorable: bool) -> dict[str, Any]:
        """Describe a single backup file for the GUI."""
        label = ""
        created = None
        m = _TIMESTAMP_RE.search(path.name)
        if m:
            ymd, hms = m.group(1), m.group(2)
            label = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]} {hms[0:2]}:{hms[2:4]}:{hms[4:6]}"
            try:
                dt = datetime(
                    int(ymd[0:4]),
                    int(ymd[4:6]),
                    int(ymd[6:8]),
                    int(hms[0:2]),
                    int(hms[2:4]),
                    int(hms[4:6]),
                    tzinfo=UTC,
                )
                created = dt.timestamp()
            except ValueError:
                created = None
        try:
            stat = path.stat()
            size = stat.st_size
            modified = stat.st_mtime
        except OSError:
            size = 0
            modified = None
        return {
            "category": category,
            "filename": path.name,
            "label": label,
            "size": size,
            "modified": modified,
            "created": created,
            "restorable": restorable,
        }

    # ------------------------------------------------------------------
    # Restore
    # ------------------------------------------------------------------

    def restore(self, category: str, filename: str) -> dict[str, Any]:
        """Restore *filename* from *category* back to its target file.

        A safety snapshot of the current target is created first, so a
        restore itself can be undone.  Raises ``ValueError`` for unknown
        categories or unsafe file names.
        """
        target = self._restore_target(category)
        if target is None:
            raise ValueError(f"Category '{category}' cannot be restored")

        backup_path = self._resolve_backup(category, filename)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            self._manager.create_backup(target, category=category)
        except OSError as exc:
            log.warning("Pre-restore snapshot failed for %s: %s", target, exc)

        self._manager.restore_backup(backup_path, target)
        return {
            "status": "ok",
            "category": category,
            "filename": filename,
            "target": str(target),
        }

    # ------------------------------------------------------------------
    # Create on demand
    # ------------------------------------------------------------------

    def create_now(self, targets: list[str]) -> dict[str, Any]:
        """Create backups of the requested targets immediately.

        Supported targets: ``config``, ``actions``, ``plugin_registry``.
        Returns the created backups and the targets that were skipped
        (missing source or content unchanged / coalesced).
        """
        created: list[dict[str, str]] = []
        skipped: list[str] = []
        for target in targets:
            source = self._target_source(target)
            category = self._target_category(target)
            if source is None or category is None or not source.exists():
                skipped.append(target)
                continue
            try:
                bak = self._manager.create_backup(source, category=category)
            except OSError as exc:
                log.warning("Backup failed for %s: %s", source, exc)
                skipped.append(target)
                continue
            if bak is None:
                skipped.append(target)
            else:
                created.append(
                    {"target": target, "category": category, "path": str(bak)}
                )
        return {"created": created, "skipped": skipped}

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _target_source(target: str) -> Path | None:
        """Return the source file for a ``create_now`` target."""
        if target == "config":
            return core.paths.get_config_file()
        if target == "actions":
            return _actions_path()
        if target == "plugin_registry":
            return core.paths.get_root_dir() / "data" / "api_plugin_registry.json"
        return None

    @staticmethod
    def _target_category(target: str) -> str | None:
        """Return the backup category used for a ``create_now`` target."""
        if target in ("config", "actions", "plugin_registry"):
            return target
        return None

    def _restore_target(self, category: str) -> Path | None:
        """Map a backup category to its restore target (or ``None``)."""
        fixed = _fixed_target(category)
        if fixed is not None:
            return fixed
        if category == "actions":
            return _actions_path()
        if category.startswith("plugins/"):
            name = category[len("plugins/") :]
            if not name or not name.isidentifier():
                return None
            return core.paths.get_plugins_dir() / name / "config.yaml"
        return None

    def _resolve_backup(self, category: str, filename: str) -> Path:
        """Resolve a backup file inside *category*, rejecting traversal."""
        if not filename or Path(filename).name != filename:
            raise ValueError("Invalid backup file name")
        cat_dir = (self._manager.backup_root / category).resolve()
        candidate = (cat_dir / filename).resolve()
        if candidate.parent != cat_dir or not candidate.is_file():
            raise ValueError(f"Backup file not found: {filename}")
        return candidate
