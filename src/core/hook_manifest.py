from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


class HookManifest:
    """Represents a parsed ``hook.json`` manifest.

    Mirrors a subset of ``PluginManifest`` — hooks are simpler than
    plugins because they run in-process and don't need entry_point,
    lifecycle management, or process-level health tracking.
    """

    def __init__(self, data: dict) -> None:
        self.name: str = data.get("name", "")
        self.version: str = data.get("version", "1.0.0")
        self.display_name: str = data.get("display_name", self.name)
        self.description: str = data.get("description", "")
        self.author: str = data.get("author", "")
        self.min_api_version: str = data.get("min_api_version", "1.0.0")
        self.capabilities: list[str] = data.get("capabilities", [])
        self.plugin: str = data.get("plugin", "")
        self.config_schema: Optional[dict] = data.get("config_schema")
        self.update_url: str = data.get("update_url", "")
        self.depends_on: list[str] = data.get("depends_on", [])

    @property
    def valid(self) -> bool:
        return bool(self.name)


def load_hook_manifest(hook_dir: Path) -> Optional[HookManifest]:
    """Read ``hook.json`` from a hook directory.

    Returns ``None`` if the file doesn't exist or is invalid.
    """
    manifest_path = hook_dir / "hook.json"
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        manifest = HookManifest(data)
        if not manifest.valid:
            log.warning("Invalid hook manifest (missing name): %s", manifest_path)
            return None
        return manifest
    except Exception as exc:
        log.warning("Failed to load hook manifest %s: %s", manifest_path, exc)
        return None


def discover_hooks_dirs() -> list[Path]:
    """Return all directories that should be scanned for hooks.

    Scans:
    1. ``event_hooks/`` — standalone hooks shipped with the tool
    2. ``plugins/*/hooks/`` — hooks bundled with specific plugins
    """
    from core.paths import get_root_dir

    root = get_root_dir()
    dirs: list[Path] = []

    # Main hooks directory (dev or release layout)
    dev_hooks = root / "src" / "event_hooks"
    rel_hooks = root / "event_hooks"
    main_hooks = dev_hooks if dev_hooks.is_dir() else rel_hooks
    if main_hooks.is_dir():
        dirs.append(main_hooks)

    # Plugin-bundled hooks
    dev_plugins = root / "src" / "plugins"
    rel_plugins = root / "plugins"
    plugins_dir = dev_plugins if dev_plugins.is_dir() else rel_plugins
    if plugins_dir.is_dir():
        for child in sorted(plugins_dir.iterdir()):
            if child.is_dir():
                hook_dir = child / "hooks"
                if hook_dir.is_dir():
                    dirs.append(hook_dir)

    return dirs


def read_hook_version(hook_dir: Path) -> str:
    """Read the hook's version from ``hook.json`` manifest."""
    manifest = load_hook_manifest(hook_dir)
    if manifest:
        return manifest.version
    return "0.0.0"
