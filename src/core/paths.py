#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from typing import Final

SUFFIX = ".exe" if sys.platform == "win32" else ".bin"

# User-data directories that identify "user data lives here" (P3a §3).
_USER_DATA_DIRS: Final[tuple[str, ...]] = ("config", "data", "server", "versions")


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_root_dir() -> Path:
    """Return the install root (dev repo root or release unpack root).

    Resolution walks up from ``get_base_dir()`` and stops at the first
    project marker: the dev marker ``src/core/paths.py`` or the release
    marker ``config/config.yaml``. Falls back to ``base.parent.parent``
    when no marker exists.
    """
    base = get_base_dir()
    # Walk up the directory tree looking for known project-root markers.
    #   Dev marker:   src/core/paths.py
    #   Rel marker:   config/config.yaml
    # This works regardless of exe nesting depth (start.exe → 1 level,
    # app.exe → 2 levels, plugins → 3 levels).
    for parent in [base] + list(base.parents):
        if (parent / "src" / "core" / "paths.py").exists():
            return parent.resolve()
        if (parent / "config" / "config.yaml").exists():
            return parent.resolve()
    return base.parent.parent.resolve()


def get_gifts_file() -> Path:
    """Return the runtime gift catalog (``core/gifts.json``).

    Resolution contract mirrors ``_load_gifts`` in the actions route:
    the synced file at ``<root>/core/gifts.json`` wins over the shipped
    factory template ``<root>/defaults/gifts.json``.
    """
    return get_root_dir().resolve() / "core" / "gifts.json"


def get_base_file() -> Path:
    """Return the main executable location (P3a-aware).

    With a versioned layout, prefers the active ``app-<ver>/`` directory
    (checking both ``app-<ver>/main{SUFFIX}`` and the nested ``core/``);
    otherwise falls back to the historic base-dir behavior.
    """
    active = get_active_app_dir()
    if active is not None:
        top = active / f"main{SUFFIX}"
        if top.is_file():
            return top.resolve()
        nested = active / "core" / f"main{SUFFIX}"
        if nested.is_file():
            return nested.resolve()
    return (get_base_dir() / f"main{SUFFIX}").resolve()


def _alt_data_home() -> Path | None:
    """Return the platform-specific alternate data home, or ``None``.

    Windows: ``%LOCALAPPDATA%/Tiktok2Mc``; Linux/macOS:
    ``~/.local/share/Tiktok2Mc``. Only honored by :func:`get_data_home_base`
    when the directory actually carries user data.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            return None
        return Path(base) / "Tiktok2Mc"
    return (Path.home() / ".local" / "share" / "Tiktok2Mc").resolve()


def get_active_app_dir() -> Path | None:
    """Return the active versioned ``app-<ver>/`` directory, or ``None``.

    ``None`` means: legacy/install-flat layout or dev tree — callers must
    keep working unchanged in that case.
    """
    try:
        # Lazy import: ``core.update_engine`` imports ``core.logger`` which
        # imports ``core.paths`` — a module-level import here would cycle.
        from core.update_engine.pointer import resolve_active_app_dir

        return resolve_active_app_dir(get_root_dir())
    except ImportError:
        # Older release binaries may not ship ``update_engine`` yet;
        # degrade to the legacy layout instead of failing.
        return None


def get_data_home_base() -> Path:
    """Return the base directory that holds user data (P3a §3).

    Resolution order:

    1. ``T2M_DATA_HOME`` environment override (test-only hook, mirrors
       ``TIKTOK2MC_UPDATE_SOURCE`` — must win over every auto-detection).
    2. Versioned layout detected under the install root → the root itself.
    3. User data already lives at the install root (legacy/dev) → root.
    4. Alternate home (``%LOCALAPPDATA%/Tiktok2Mc`` / ``~/.local/share/...``)
       — only when it already exists there.
    5. Install root (fresh legacy install, nothing exists yet).
    """
    override = os.environ.get("T2M_DATA_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    root = get_root_dir()

    if get_active_app_dir() is not None:
        return root

    if (root / "config" / "config.yaml").is_file() or any(
        (root / name).is_dir() for name in _USER_DATA_DIRS
    ):
        return root

    alt = _alt_data_home()
    if alt is not None and any((alt / name).is_dir() for name in _USER_DATA_DIRS):
        return alt

    return root


def get_config_file() -> Path:
    """Return the user config file (config/config.yaml, data-home aware)."""
    root = get_data_home_base()
    return (root / "config" / "config.yaml").resolve()


def get_chatbot_config_file() -> Path:
    """Return the chatbot's own config file (config/chatbot.yaml)."""
    root = get_data_home_base()
    return (root / "config" / "chatbot.yaml").resolve()


def get_chatbot_session_file() -> Path:
    """Return the encrypted chatbot session store (data/chatbot_session.json)."""
    root = get_data_home_base()
    return (root / "data" / "chatbot_session.json").resolve()


def get_runtime_dir() -> Path:
    """Return the runtime IPC directory (core/runtime, data-home aware)."""
    root = get_data_home_base()
    return (root / "core" / "runtime").resolve()


def get_plugin_data_dir() -> Path:
    """Return the namespaced per-plugin/hook storage directory.

    Each extension gets its own ``<namespace>.json`` file inside this
    directory (see ``core.api.services.persistence_service``).
    """
    root = get_data_home_base()
    return (root / "data" / "plugin_data").resolve()


def get_plugin_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        import __main__

        return Path(__main__.__file__).resolve().parent
    except (AttributeError, ImportError):
        return Path(sys.executable).resolve().parent


def get_plugin_config_file() -> Path:
    return get_plugin_dir() / "config.yaml"


def get_plugins_dir() -> Path:
    """Return the resolved plugins directory (dev, versioned, or legacy)."""
    root = get_root_dir()
    dev_dir = root / "src" / "plugins"
    if dev_dir.is_dir():
        return dev_dir
    # P3a: inside a versioned app dir, plugins ship per version.
    active = get_active_app_dir()
    if active is not None and (active / "plugins").is_dir():
        return (active / "plugins").resolve()
    rel_dir = root / "plugins"
    if rel_dir.is_dir():
        return rel_dir
    return dev_dir


def get_versions_dir() -> Path:
    """Return the resolved versions directory (template repository)."""
    return (get_data_home_base() / "versions").resolve()


def get_servers_dir() -> Path:
    """Return the resolved server instances directory (server/<instance>/)."""
    return (get_data_home_base() / "server").resolve()
