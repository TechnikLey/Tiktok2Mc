"""``current.json`` pointer management for versioned app updates.

The pointer is the single source of truth for which ``app-<ver>/`` directory
is active. Writers are the updater binary only; every reader has a fallback
that never propagates a corrupt state to callers (see
:func:`resolve_active_app_dir`).

Security notes:

- ``active_app_dir`` / ``previous_app_dir`` are validated against the
  ``app-<version>`` pattern: they may never contain path separators or
  ``..``, so a corrupt/hostile pointer cannot direct processes outside the
  install root.
- Writes are atomic (tmp file + ``os.replace``) so readers never see a
  half-written pointer.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import asdict, dataclass

# NOTE: plain stdlib logger — ``core.logger.initialize_logging`` performs
# filesystem work (log dir creation) and must not run at module import time:
# this module is imported lazily from ``core.paths`` inside test sessions
# where the write guard is active.
from logging import Logger, getLogger
from pathlib import Path
from typing import Any, Final

from packaging.version import InvalidVersion, Version

log: Logger = getLogger(__name__)

APP_DIR_PREFIX: Final[str] = "app-"
POINTER_FILE: Final[str] = "current.json"
_POINTER_TMP_SUFFIX: Final[str] = ".tmp"

_WRITE_LOCK = threading.Lock()


class PointerError(ValueError):
    """Raised when pointer data is structurally invalid for writing."""


@dataclass(frozen=True)
class AppPointer:
    """Content of one ``current.json`` pointer file."""

    active_app_dir: str
    tool_version: str
    installed_at_utc: str | None = None
    manifest_sha256: str | None = None
    previous_app_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a plain-dict representation for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Any) -> AppPointer:
        """Validate and build a pointer from parsed JSON data.

        Raises :class:`PointerError` when required fields are missing or a
        directory reference attempts to escape the install root.
        """
        if not isinstance(data, dict):
            msg = "pointer payload must be a JSON object"
            raise PointerError(msg)

        def _require(name: str) -> str:
            value = data.get(name)
            if not isinstance(value, str) or not value:
                msg = f"pointer field '{name}' must be a non-empty string"
                raise PointerError(msg)
            return value

        active = _require("active_app_dir")
        tool_version = _require("tool_version")
        _validate_dir_name(active)
        previous = data.get("previous_app_dir")
        if previous is not None:
            if not isinstance(previous, str) or not previous:
                msg = "pointer field 'previous_app_dir' must be a string"
                raise PointerError(msg)
            _validate_dir_name(previous)

        installed = data.get("installed_at_utc")
        manifest_sha = data.get("manifest_sha256")
        if installed is not None and not isinstance(installed, str):
            installed = None
        if manifest_sha is not None and not isinstance(manifest_sha, str):
            manifest_sha = None

        return cls(
            active_app_dir=active,
            tool_version=tool_version,
            installed_at_utc=installed,
            manifest_sha256=manifest_sha,
            previous_app_dir=previous,
        )


def _validate_dir_name(name: str) -> None:
    """Ensure *name* looks like ``app-<version>`` and stays within the root."""
    if not name.startswith(APP_DIR_PREFIX):
        msg = f"app dir name must start with '{APP_DIR_PREFIX}': {name!r}"
        raise PointerError(msg)
    rest = name[len(APP_DIR_PREFIX) :]
    if any(c in rest for c in ("/", "\\", "..", ":")):
        msg = f"app dir name must not contain path separators: {name!r}"
        raise PointerError(msg)
    try:
        Version(rest)
    except InvalidVersion as exc:
        msg = f"app dir name is not a version: {name!r}"
        raise PointerError(msg) from exc


def pointer_path(root: Path) -> Path:
    """Return the filesystem path of the pointer file under *root*."""
    return root / POINTER_FILE


def scan_app_dirs(root: Path) -> list[tuple[Path, Version]]:
    """Return all ``app-<version>`` directories under *root*, oldest first."""
    result: list[tuple[Path, Version]] = []
    if not root.is_dir():
        return result
    for child in sorted(root.iterdir()):
        if not child.is_dir() or not child.name.startswith(APP_DIR_PREFIX):
            continue
        rest = child.name[len(APP_DIR_PREFIX) :]
        try:
            version = Version(rest)
        except InvalidVersion:
            log.debug("Ignoring non-version app dir: %s", child.name)
            continue
        result.append((child, version))
    result.sort(key=lambda pair: pair[1])
    return result


def read_pointer(root: Path) -> AppPointer | None:
    """Read and validate the pointer under *root*.

    Returns ``None`` when the file is missing, unreadable or payload-invalid
    so callers can apply their own fallback (never fail on a corrupt
    pointer).
    """
    path = pointer_path(root)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return AppPointer.from_dict(data)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        # PointerError subclasses ValueError; JSONDecodeError subclasses ValueError.
        log.warning("Ignoring invalid update pointer %s: %s", path, exc)
        return None


def write_pointer(root: Path, pointer: AppPointer) -> Path:
    """Atomically write *pointer* under *root* and return the final path.

    Uses a temp file plus ``os.replace`` so concurrent readers never observe
    a partially written file.
    """
    root.mkdir(parents=True, exist_ok=True)
    final_path = pointer_path(root)
    tmp_path = root / (POINTER_FILE + _POINTER_TMP_SUFFIX)
    payload = json.dumps(pointer.to_dict(), indent=2) + "\n"
    with _WRITE_LOCK:
        with tmp_path.open("w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, final_path)
    return final_path


def resolve_active_app_dir(root: Path) -> Path | None:
    """Resolve the active versioned app directory under *root*.

    Resolution order:

    1. Valid pointer whose ``active_app_dir`` directory actually exists.
    2. Newest ``app-<version>`` directory (pointer missing/corrupt/stale).
    3. ``None`` when no versioned layout exists at all (legacy install).

    Callers are expected to treat ``None`` as "stay in legacy layout".
    """
    pointer = read_pointer(root)
    if pointer is not None:
        active = root / pointer.active_app_dir
        if active.is_dir():
            return active
        log.warning(
            "Pointer references missing app dir %s; falling back to newest",
            pointer.active_app_dir,
        )
    candidates = scan_app_dirs(root)
    if candidates:
        return candidates[-1][0]
    return None


def prune_versions(
    root: Path, active_dir_name: str, previous_dir_name: str | None = None
) -> list[str]:
    """Delete all ``app-<version>`` dirs except *active* and *previous*.

    Returns the list of directory names that were removed. Dirs whose names
    do not parse as ``app-<version>`` are never touched.
    """
    keep: set[str] = {active_dir_name}
    if previous_dir_name:
        keep.add(previous_dir_name)
    removed: list[str] = []
    for child, _ in scan_app_dirs(root):
        if child.name in keep:
            continue
        try:
            shutil.rmtree(child)
            removed.append(child.name)
            log.info("Pruned old app version dir: %s", child.name)
        except OSError as exc:
            log.warning("Could not prune app dir %s: %s", child.name, exc)
    return removed
