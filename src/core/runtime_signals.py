"""Runtime signal files (``core/runtime/``) — supervisor IPC.

Signal files such as ``plugin_start_<name>`` / ``plugin_stop_<name>``
are process communication between the API routes (or the CLI) and the
supervisor's signal watcher — not configuration.  All producers must
use these helpers so the file-naming convention lives in exactly one
place.
"""

from __future__ import annotations

import logging
from pathlib import Path

import core.paths

log = logging.getLogger(__name__)


def runtime_dir() -> Path:
    """Return (and create) the runtime signal directory."""
    d = core.paths.get_root_dir() / "core" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plugin_signal_path(plugin_name: str, action: str) -> Path:
    """Path of a plugin lifecycle signal file."""
    return runtime_dir() / f"plugin_{action}_{plugin_name}"


def write_plugin_signal(plugin_name: str, action: str) -> bool:
    """Write a plugin lifecycle signal file for the supervisor watcher.

    Returns ``True`` if the signal was written successfully.
    """
    signal_file = plugin_signal_path(plugin_name, action)
    try:
        signal_file.write_text(plugin_name, encoding="utf-8")
        return True
    except OSError as exc:
        log.warning("Failed to write plugin signal %s: %s", signal_file, exc)
        return False


def clean_plugin_signals(plugin_name: str) -> None:
    """Remove all runtime signal files for a plugin."""
    for action in ("start", "stop"):
        p = plugin_signal_path(plugin_name, action)
        try:
            if p.exists():
                p.unlink()
        except OSError as exc:
            log.warning("Failed to clean signal %s: %s", p, exc)
