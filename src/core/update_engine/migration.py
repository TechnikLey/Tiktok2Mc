"""One-time migration of legacy flat layouts into versioned app dirs (P3a §8).

Legacy layout (pre-P3a release)::

    <root>/
    ├── start{.exe|.bin}            ← stays
    ├── core/                       ← program binaries (plus user runtime!)
    │   ├── main{.exe|.bin} ...
    │   └── runtime/                ← stays (user data, not program)
    ├── plugins/                    ← program content, moves
    ├── config|data|server/         ← stays (user data)
    └── version.txt                 ← ToolVersion:/UpdaterVersion:

Target layout::

    <root>/app-<ver>/core|plugins/...
    <root>/current.json + core/runtime + user data

Properties:

- **Idempotent**: already-migrated or partially-migrated trees are detected
  and completed without moving anything twice.
- **Abort-safe**: steps are unconditionally re-executed on every call; each
  one skips anything already at its target, so a crash (or a lost journal)
  is simply completed on the next start. The
  ``core/runtime/migration_state.json`` journal remains for observability.
- **Never touches user data** (``config/``, ``data/``, ``server/``,
  ``versions/``, ``core/runtime/``).

Runs at launcher start (no processes running ⇒ no file locks on Windows).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from logging import Logger, getLogger
from pathlib import Path
from typing import Any, Final

from core.paths import SUFFIX, get_runtime_dir

log: Logger = getLogger(__name__)

STATE_FILE: Final[str] = "migration_state.json"
VERSION_FILE_NAME: Final[str] = "version.txt"
_RUNTIME_DIR_NAME: Final[str] = "runtime"
_POINTER_FILE_NAME: Final[str] = "current.json"

_STATE_DONE: Final[str] = "done"
_STATE_RUNNING: Final[str] = "running"


@dataclass(frozen=True)
class MigrationResult:
    """Outcome of :func:`migrate_install`."""

    migrated: bool
    app_dir: Path | None
    reason: str


# ---------------------------------------------------------------------------
# version.txt parsing — shared by updater and migration (single source).
# ---------------------------------------------------------------------------

_VERSION_RE: Final = re.compile(r"(\d+\.\d+(?:\.\d+)?(?:-\w+)?)")


def extract_version(text: str | None) -> str:
    """Extract the first ``x.y(.z)`` version substring, or ``0.0.0``."""
    if not text:
        return "0.0.0"
    match = _VERSION_RE.search(str(text))
    return match.group(1) if match else "0.0.0"


def parse_version_txt(path: Path) -> dict[str, str]:
    """Parse a release ``version.txt`` into ``{"tool": .., "updater": ..}``."""
    versions = {"tool": "0.0.0", "updater": "0.0.0"}
    if not path.is_file():
        log.error("Version file not found: %s", path)
        return versions
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" not in line:
                continue
            key, value = map(str.strip, line.split(":", 1))
            lowered = key.lower()
            if "toolversion" in lowered:
                versions["tool"] = extract_version(value)
            elif "updaterversion" in lowered:
                versions["updater"] = extract_version(value)
    except OSError as exc:
        log.error("Could not read version file %s: %s", path, exc)
    return versions


# ---------------------------------------------------------------------------
# Migration state (resume journal)
# ---------------------------------------------------------------------------


def _state_path() -> Path:
    return get_runtime_dir() / STATE_FILE


def read_state() -> dict[str, Any] | None:
    """Read the migration journal, or ``None`` when absent/corrupt."""
    path = _state_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("Ignoring corrupt migration state %s", path)
        return None
    return data if isinstance(data, dict) else None


def _write_state(state: dict[str, Any]) -> None:
    """Best-effort atomic journal write; failures only cost resume safety."""
    path = _state_path()
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("Could not persist migration state: %s", exc)


# ---------------------------------------------------------------------------
# Detection + migration
# ---------------------------------------------------------------------------


def is_legacy_install(root: Path) -> bool:
    """True when *root* still has flat program content to migrate.

    Requires: a ``version.txt`` (release layouts only — protects dev trees),
    program binaries directly under ``core/``, and **no ``current.json``**.

    Note: partially existing ``app-<ver>/`` directories do NOT disqualify —
    a crashed migration legitimately leaves one behind and must resume.
    """
    if not root.is_dir():
        return False
    if not (root / VERSION_FILE_NAME).is_file():
        return False
    if (root / _POINTER_FILE_NAME).is_file():
        return False
    core_dir = root / "core"
    return core_dir.is_dir() and any(core_dir.glob(f"*{SUFFIX}"))


def migrate_install(root: Path, *, tool_version: str | None = None) -> MigrationResult:
    """Migrate a legacy flat install under *root* into the versioned layout.

    Safe to call repeatedly (idempotent) and crash-resumable via the
    journal. Never moves user data.
    """
    root = root.resolve()

    if not is_legacy_install(root):
        result_app = _existing_active_dir(root)
        if result_app is not None:
            return MigrationResult(False, result_app, "already_versioned")
        return MigrationResult(False, None, "nothing_to_migrate")

    versions = parse_version_txt(root / VERSION_FILE_NAME)
    resolved_version = tool_version or versions["tool"]
    if not resolved_version or resolved_version == "0.0.0":
        log.error("Cannot determine install version for migration")
        return MigrationResult(False, None, "missing_version")

    app_dir = root / f"app-{resolved_version}"
    core_target = app_dir / "core"
    state = read_state() or {"steps_done": [], "app_dir": None}
    steps: set[str] = set(state.get("steps_done", []))
    app_dir.mkdir(parents=True, exist_ok=True)
    core_target.mkdir(parents=True, exist_ok=True)

    # Step 1: move program content out of core/ (runtime/ stays = user data).
    # Always executed: per-item "target exists → skip" makes this idempotent,
    # so a crash or lost journal costs nothing.
    if "move_core" not in steps:
        log.info("Resuming core program-content move (step missing from journal)")
    source_core = root / "core"
    for child in sorted(source_core.iterdir()):
        if child.name == _RUNTIME_DIR_NAME:
            continue
        target = core_target / child.name
        if target.exists():
            continue  # already moved (crash/resume or idempotence)
        shutil.move(str(child), str(target))
    steps.add("move_core")
    state["steps_done"] = sorted(steps)
    state.update({"phase": _STATE_RUNNING, "app_dir": app_dir.name})
    _write_state(state)
    log.info("Moved core program content to %s", core_target)

    # Step 2: move plugins/ (shipped plugins are program content).
    if (root / "plugins").is_dir():
        target = app_dir / "plugins"
        if not target.exists():
            shutil.move(str(root / "plugins"), str(target))
        steps.add("move_plugins")
        state["steps_done"] = sorted(steps)
        _write_state(state)
        log.info("Moved plugins to %s", target)

    # Step 3: write the pointer (idempotent final write).
    from core.update_engine.pointer import AppPointer, write_pointer

    write_pointer(
        root,
        AppPointer(
            active_app_dir=app_dir.name,
            tool_version=resolved_version,
        ),
    )
    steps.add("write_pointer")
    state["steps_done"] = sorted(steps)

    state["phase"] = _STATE_DONE
    _write_state(state)
    log.info("Migration to versioned layout complete: %s", app_dir)
    return MigrationResult(True, app_dir, "migrated")


def _existing_active_dir(root: Path) -> Path | None:
    """Return the newest ``app-<ver>/`` dir, or ``None`` for flat layouts."""
    from core.update_engine.pointer import scan_app_dirs

    candidates = scan_app_dirs(root)
    return candidates[-1][0] if candidates else None
