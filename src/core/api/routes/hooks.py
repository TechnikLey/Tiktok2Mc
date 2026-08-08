"""Hook management API endpoints.

Provides discovery, enable/disable, config CRUD, and status for
the hook system. Mirrors the plugin management pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from ruamel.yaml.error import YAMLError

from core.hook_manifest import (
    HookManifest,
    discover_hooks_dirs,
    load_hook_manifest,
)
from core.hook_registry import HookRegistration, get_hook_registry
from core.plugin_config import save_plugin_config
from core.yaml_utils import load_yaml

log = logging.getLogger(__name__)

router = APIRouter(tags=["Hooks"])


# ── Hook cache ────────────────────────────────────────────────────────
# Avoid redundant filesystem scans on every hook listing.

_hook_cache: dict[str, tuple[Path, HookManifest]] | None = None


def _build_hook_cache() -> dict[str, tuple[Path, HookManifest]]:
    """Scan all hook directories once and return {name: (path, manifest)}."""
    cache: dict[str, tuple[Path, HookManifest]] = {}
    for parent_dir in discover_hooks_dirs():
        for child in sorted(parent_dir.iterdir()):
            if not child.is_dir():
                continue
            manifest = load_hook_manifest(child)
            if manifest and manifest.name:
                cache[manifest.name] = (child, manifest)
    return cache


def _invalidate_hook_cache() -> None:
    global _hook_cache
    _hook_cache = None


def _get_hook_cache() -> dict[str, tuple[Path, HookManifest]]:
    global _hook_cache
    if _hook_cache is None:
        _hook_cache = _build_hook_cache()
    return _hook_cache


def _find_hook_dir(hook_name: str) -> Path | None:
    entry = _get_hook_cache().get(hook_name)
    return entry[0] if entry else None


def _serialize_hook(reg: HookRegistration) -> dict:
    """Convert a HookRegistration to a JSON-safe dict."""
    d = reg.to_dict()
    entry = _get_hook_cache().get(reg.name)
    if entry:
        hook_dir, manifest = entry
        d["path"] = str(hook_dir)
        if manifest.config_schema:
            d["config_schema"] = manifest.config_schema
        # If registry has an error but disk loaded fine, clear it
        if d.get("error"):
            d["error"] = ""
    return d


# ── List / Discover ────────────────────────────────────────────────────


@router.get("/hooks")
async def list_hooks():
    """List all registered hooks with their status.

    If the registry is empty, auto-discovers hooks from the filesystem
    so they appear immediately without waiting for the bridge process.
    """
    registry = get_hook_registry()
    hooks = registry.list()
    if not hooks:
        from core.hook_loader import _discover_hook_dirs
        discovered = _discover_hook_dirs()
        hook_infos = []
        for info in discovered:
            hook_infos.append({
                "name": info["name"],
                "version": info["version"],
                "display_name": info["display_name"],
                "description": info["description"],
                "author": info["author"],
                "capabilities": info["capabilities"],
                "plugin": info["plugin"],
                "update_url": info["update_url"],
                "source": info["source"],
            })
        registry.sync_from_discovery(hook_infos)
        active_names = {info["name"] for info in discovered}
        registry.clean_stale(active_names)
        _invalidate_hook_cache()
        hooks = registry.list()
        log.info("[HOOK] Auto-discovered %d hook(s) on first list request", len(hooks))
    serialized = [_serialize_hook(h) for h in hooks]
    return {
        "total": len(serialized),
        "enabled": sum(1 for h in serialized if h["enabled"]),
        "hooks": serialized,
    }


@router.post("/hooks/discover")
async def discover_hooks():
    """Scan hook directories and register any new hooks.

    Returns the updated hook list.
    """
    from core.hook_loader import _discover_hook_dirs

    discovered = _discover_hook_dirs()
    registry = get_hook_registry()

    hook_infos = []
    for info in discovered:
        hook_infos.append({
            "name": info["name"],
            "version": info["version"],
            "display_name": info["display_name"],
            "description": info["description"],
            "author": info["author"],
            "capabilities": info["capabilities"],
            "plugin": info["plugin"],
            "update_url": info["update_url"],
            "source": info["source"],
        })

    new_count = registry.sync_from_discovery(hook_infos)

    # Clean stale
    active_names = {info["name"] for info in discovered}
    cleaned = registry.clean_stale(active_names)

    _invalidate_hook_cache()
    hooks = [_serialize_hook(h) for h in registry.list()]
    return {
        "total": len(hooks),
        "enabled": sum(1 for h in hooks if h["enabled"]),
        "new": new_count,
        "removed": cleaned,
        "hooks": hooks,
    }


# ── Single hook ────────────────────────────────────────────────────────


@router.get("/hooks/{name}")
async def get_hook(name: str):
    """Get details for a single hook."""
    registry = get_hook_registry()
    hook = registry.get(name)
    if hook is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found")
    return _serialize_hook(hook)


# ── Enable / Disable ──────────────────────────────────────────────────


@router.post("/hooks/{name}/enable")
async def enable_hook(name: str):
    """Enable a hook. Requires a restart to take effect."""
    registry = get_hook_registry()
    hook = registry.get(name)
    if hook is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found")
    if hook.enabled:
        return {"status": "already_enabled", "name": name}
    registry.set_enabled(name, True)
    _invalidate_hook_cache()
    return {"status": "enabled", "name": name}


@router.post("/hooks/{name}/disable")
async def disable_hook(name: str):
    """Disable a hook. Requires a restart to take effect."""
    registry = get_hook_registry()
    hook = registry.get(name)
    if hook is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found")
    if not hook.enabled:
        return {"status": "already_disabled", "name": name}
    registry.set_enabled(name, False)
    _invalidate_hook_cache()
    return {"status": "disabled", "name": name}


# ── Config ─────────────────────────────────────────────────────────────


@router.get("/hooks/{name}/config")
async def get_hook_config(name: str):
    """Get the per-hook config for a named hook."""
    hook_dir = _find_hook_dir(name)
    if hook_dir is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found on disk")

    config_path = hook_dir / "config.yaml"
    if config_path.exists():
        try:
            config = load_yaml(config_path) or {}
        except (OSError, ValueError, YAMLError) as exc:
            raise HTTPException(status_code=500, detail=f"Failed to load config: {exc}")
    else:
        config = {}

    return {"name": name, "config": config}


@router.put("/hooks/{name}/config")
async def update_hook_config(name: str, body: dict):
    """Update the per-hook config for a named hook."""
    hook_dir = _find_hook_dir(name)
    if hook_dir is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found on disk")

    new_config = body.get("config", {})
    try:
        save_plugin_config(hook_dir, new_config, backup=True)
    except (OSError, ValueError, YAMLError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {exc}")

    return {"status": "saved", "name": name}


@router.get("/hooks/{name}/config/schema")
async def get_hook_config_schema(name: str):
    """Get the config schema for a hook (from hook.json)."""
    hook_dir = _find_hook_dir(name)
    if hook_dir is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found on disk")

    manifest = load_hook_manifest(hook_dir)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"No hook.json found for '{name}'")

    return {
        "name": name,
        "config_schema": manifest.config_schema or {},
    }
