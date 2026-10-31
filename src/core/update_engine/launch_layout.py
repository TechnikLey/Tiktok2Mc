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

import os

# NOTE: plain stdlib logger — see pointer.py for the import-time rationale.
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


# ---------------------------------------------------------------------------
# Launcher binary maintenance (P3a §7)
# ---------------------------------------------------------------------------


def swap_pending_launcher_binaries(root_dir: Path, suffix: str) -> dict[str, bool]:
    """Install queued launcher binaries (``*_new``) at the next boot.

    The updater never overwrites running binaries; it leaves
    ``start_new{suffix}`` / ``update_new{suffix}`` at the install root and
    the launcher swaps them here, before any child process is spawned:

    - ``update_new`` → ``update``: plain ``os.replace`` (update.exe is not
      running at boot).
    - ``start_new`` → ``start``: the *running* launcher binary cannot be
      deleted/overwritten, but renaming it is allowed — so the current
      binary is renamed away first, then the new one takes its place. The
      renamed leftover is deleted best-effort (only possible when that
      old image is not held by any process).

    Returns which binaries were actually swapped.
    """
    root_dir = Path(root_dir)
    swapped: dict[str, bool] = {"start": False, "update": False}

    pending = root_dir / f"update_new{suffix}"
    target = root_dir / f"update{suffix}"
    if pending.is_file():
        try:
            os.replace(pending, target)
            swapped["update"] = True
            log.info("Launcher updated: %s", target.name)
        except OSError as exc:
            log.warning("Could not install queued updater binary: %s", exc)

    pending_start = root_dir / f"start_new{suffix}"
    target_start = root_dir / f"start{suffix}"
    if pending_start.is_file():
        prev = root_dir / f"start_prev{suffix}"
        try:
            if target_start.exists():
                # Renaming a running executable is allowed on Windows;
                # it frees the current name for the replacement.
                os.replace(target_start, prev)
            os.replace(pending_start, target_start)
            swapped["start"] = True
            log.info("Launcher swapped in at boot: %s", target_start.name)
        except OSError as exc:
            log.warning(
                "Could not install queued launcher binary %s: %s", pending_start, exc
            )

    # Best-effort cleanup of a previous leftover image.
    prev = root_dir / f"start_prev{suffix}"
    if prev.exists():
        try:
            prev.unlink()
        except OSError as exc:
            log.debug("Could not delete previous launcher image %s: %s", prev, exc)

    return swapped


# ---------------------------------------------------------------------------
# First-start hook: config migration (P3a §7)
# ---------------------------------------------------------------------------


def run_first_start_config_hook(root_dir: Path) -> dict[str, object] | None:
    """Migrate user config once per new tool version (launcher boot).

    Compare the version the tool last ran with (``last_run_version.txt`` in
    the runtime dir) against the installed tool version. When they differ,
    run the template-based config migration and record the version.

    Template resolution order (first hit wins):

    1. ``<active_app_dir>/config/config.default.yaml`` (versioned layout)
    2. ``<root>/config/config.default.yaml`` (legacy/migrated layouts)

    Returns a summary dict describing what was done, or ``None`` when the
    hook was a no-op. Fail-open: any error only logs, never aborts startup.
    """
    from core.config_migration import migrate_config
    from core.paths import get_config_file, get_runtime_dir
    from core.update_engine.migration import parse_version_txt
    from core.update_engine.pointer import read_pointer

    root_dir = Path(root_dir)
    pointer = read_pointer(root_dir)
    tool_version: str | None
    if pointer is not None:
        tool_version = pointer.tool_version
    else:
        versions = parse_version_txt(root_dir / "version.txt")
        tool_version = versions.get("tool")
        if not tool_version or tool_version == "0.0.0":
            return None

    runtime_dir = get_runtime_dir()
    marker = runtime_dir / "last_run_version.txt"
    try:
        last_version = marker.read_text(encoding="utf-8").strip()
    except OSError:
        last_version = ""
    if last_version == tool_version:
        return None

    template = None
    candidates: list[Path] = []
    if pointer is not None:
        candidates.append(
            root_dir / pointer.active_app_dir / "config" / "config.default.yaml"
        )
    candidates.append(root_dir / "config" / "config.default.yaml")
    for candidate in candidates:
        if candidate.is_file():
            template = candidate
            break
    if template is None:
        log.info(
            "First-start config migration skipped: no config template found "
            "for version %s",
            tool_version,
        )
        return None

    try:
        config_file = get_config_file()
        migrated = migrate_config(config_file, template)
        runtime_dir.mkdir(parents=True, exist_ok=True)
        marker.write_text(tool_version + "\n", encoding="utf-8")
        return {
            "version": tool_version,
            "template": template,
            "migrated": migrated,
        }
    except Exception:
        log.exception("First-start config migration failed; continuing startup")
        return None
