"""Launcher-side layout resolution (P3a §7).

One function the ``start`` launcher calls at boot:

1. Migrate a legacy flat install (once, abort-safe) into the versioned layout.
2. Resolve the *app base directory* — the directory that contains the
   ``core/`` program binaries (``app.exe``, ``gui.exe``, …) for the active
   version.

Fail-open contract: any problem during migration/probing degrades to the
legacy base directory instead of preventing startup.
"""

from __future__ import annotations

from logging import Logger, getLogger
from pathlib import Path

log: Logger = getLogger(__name__)


def resolve_app_base(base_dir: Path, root_dir: Path) -> tuple[Path, bool]:
    """Return ``(app_base, migrated)`` for the launcher.

    ``app_base`` is where ``<app_base>/core/|gui...`` binaries live:

    - versioned layout → the active ``app-<ver>/`` directory
    - legacy/dev layouts → *base_dir* (unchanged behavior)

    ``migrated`` tells the caller whether this boot performed the one-time
    layout migration (for logging / first-run messaging).
    """
    from core.update_engine.migration import is_legacy_install, migrate_install
    from core.update_engine.pointer import resolve_active_app_dir

    # 1) One-time migration of a legacy install. Runs before any child
    #    process is spawned, so there are no file locks to worry about.
    migrated = False
    if is_legacy_install(root_dir):
        try:
            result = migrate_install(root_dir)
            migrated = result.migrated
            if result.app_dir is not None:
                log.info(
                    "Layout migration result: %s (%s)",
                    result.app_dir.name,
                    result.reason,
                )
        except Exception:
            log.exception("Layout migration failed; continuing with legacy layout")

    # 2) Resolve the active base (pointer → newest app dir → legacy).
    active = None
    try:
        active = resolve_active_app_dir(root_dir)
    except Exception:
        log.exception("Pointer probing failed; continuing with legacy layout")

    if active is not None:
        return active, migrated
    return base_dir, migrated
