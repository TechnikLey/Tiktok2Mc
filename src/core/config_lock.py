"""Cross-process config file locking and version tracking.

Provides ``config_transaction()`` — a context manager that acquires an
OS-level file lock around config read-modify-write operations and
bumps a monotonic version counter on success.  Readers can check the
version to detect stale data without modifying the config file.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout

from core.yaml_utils import load_yaml, save_yaml

log = logging.getLogger(__name__)

_LOCK_TIMEOUT = 10.0
_STALE_THRESHOLD = 30.0


def _version_file(config_path: Path) -> Path:
    return config_path.with_suffix(config_path.suffix + ".version")


def read_config_version(config_path: Path) -> int:
    """Return the current config version counter, or 0 if absent."""
    vf = _version_file(config_path)
    try:
        return int(vf.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return 0


def _bump_config_version(config_path: Path) -> int:
    """Increment and return the config version counter."""
    vf = _version_file(config_path)
    current = read_config_version(config_path)
    new_version = current + 1
    vf.write_text(str(new_version), encoding="utf-8")
    return new_version


def _acquire_lock(lock_path: Path) -> FileLock | None:
    """Acquire a cross-process file lock, cleaning stale locks."""
    lock = FileLock(lock_path, timeout=_LOCK_TIMEOUT)

    # Clean stale lock files left by crashed processes.
    # On Windows, OS-level locks are released on process exit, so a
    # leftover .lock file is always stale.  On POSIX, flock/fcntl locks
    # are also released, but a NFS or forced-kill edge case can leave
    # a file behind.  We remove .lock files older than _STALE_THRESHOLD.
    try:
        if lock_path.exists():
            age = time.time() - lock_path.stat().st_mtime
            if age > _STALE_THRESHOLD:
                lock_path.unlink(missing_ok=True)
                log.debug("Removed stale lock file: %s (%.0fs old)", lock_path, age)
    except OSError:
        pass

    try:
        lock.acquire()
        return lock
    except Timeout:
        log.warning("Config lock timeout after %.0fs: %s", _LOCK_TIMEOUT, lock_path)
        return None
    except OSError as exc:
        log.warning("Could not acquire config lock %s: %s", lock_path, exc)
        return None


@contextmanager
def config_transaction(
    config_path: Path,
    *,
    backup: bool = True,
) -> Generator[dict[str, Any], None, None]:
    """Atomic read-modify-write transaction for config files.

    Acquires a cross-process file lock, loads the current config, yields
    it for in-place mutation, and writes it back on success.  The config
    version counter is bumped so readers can detect changes.

    Usage::

        with config_transaction(config_path) as cfg:
            cfg["rcon"]["enabled"] = True
    """
    lock_path = config_path.with_suffix(config_path.suffix + ".lock")
    lock = _acquire_lock(lock_path)

    try:
        # Read current config inside the lock
        if config_path.exists():
            data = load_yaml(config_path)
        else:
            data = {}

        # Yield for caller to mutate
        yield data

        # Write back
        save_yaml(config_path, data, backup=backup)

        # Bump version so readers detect the change
        new_ver = _bump_config_version(config_path)
        log.debug("Config written (version %d): %s", new_ver, config_path)
    finally:
        if lock is not None:
            try:
                lock.release()
            except OSError:
                pass
