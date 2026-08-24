"""Hook management API endpoints.

Provides discovery, enable/disable, config CRUD, and status for
the hook system. Mirrors the plugin management pattern.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from ruamel.yaml.error import YAMLError

from core.api.routes.reload import _write_signal
from core.api.updater import PackageUpdateChecker
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


def _request_hook_reload(reason: str, hook_name: str) -> bool:
    """Tell the bridge process to re-register all hooks at runtime.

    Hooks read their config and register actions once at load time, so any
    enable/disable/config change needs a hook reload to take effect. The
    bridge picks the signal up within ~1 second; no restart required.
    """
    ok = _write_signal("reload_hooks", {"reason": reason, "hook": hook_name})
    if not ok:
        log.warning(
            "[HOOK] Could not write reload signal — change applies after restart"
        )
    return ok


# ── Hook dashboard widgets ────────────────────────────────────────────
# Hooks with the "ui" permission can contribute HTML cards to the web
# dashboard. Storage is in-memory: widgets are re-registered by the hook's
# register() after every (re)load, so a restart simply starts empty.

_hook_widgets: dict[str, dict[str, str]] = {}
_hook_widgets_lock = threading.Lock()
_WIDGET_HTML_MAX = 256 * 1024  # generous cap; widgets are small snippets


@router.get("/hooks/widgets")
async def list_hook_widgets():
    """List all registered dashboard widgets (title only, no HTML)."""
    with _hook_widgets_lock:
        widgets = [
            {"name": name, "title": entry["title"]}
            for name, entry in sorted(_hook_widgets.items())
        ]
    return {"widgets": widgets}


@router.post("/hooks/{name}/widget")
async def register_hook_widget(name: str, body: dict):
    """Register/replace a hook's dashboard widget.

    Called by the bridge on behalf of a hook whose manifest grants the
    ``ui`` permission. Unknown hooks are rejected so arbitrary processes
    cannot inject UI content.
    """
    title = str(body.get("title") or name)[:200]
    html = body.get("html")
    if not isinstance(html, str) or not html.strip():
        raise HTTPException(status_code=422, detail="'html' must be a non-empty string")
    if len(html) > _WIDGET_HTML_MAX:
        raise HTTPException(status_code=422, detail="widget html too large")
    if name not in _get_hook_cache():
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found")
    with _hook_widgets_lock:
        _hook_widgets[name] = {"title": title, "html": html}
    log.info("[HOOK] Dashboard widget registered for '%s'", name)
    return {"status": "ok"}


@router.delete("/hooks/{name}/widget")
async def delete_hook_widget(name: str):
    """Remove a hook's widget (called when the hook is disabled/deleted)."""
    with _hook_widgets_lock:
        removed = _hook_widgets.pop(name, None)
    return {"status": "ok", "removed": removed is not None}


@router.get("/hooks/{name}/widget")
async def get_hook_widget(name: str):
    """Return a hook's widget as ``{"name", "title", "html"}``."""
    with _hook_widgets_lock:
        entry = _hook_widgets.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No widget for hook '{name}'")
    return {"name": name, "title": entry["title"], "html": entry["html"]}


@router.get("/hooks/{name}/widget.html")
async def get_hook_widget_page(name: str):
    """Serve a hook's widget as a standalone HTML document (iframe target).

    The snippet is embedded in a minimal transparent page so it blends
    into the dashboard's dark theme.
    """
    from starlette.responses import HTMLResponse

    with _hook_widgets_lock:
        entry = _hook_widgets.get(name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No widget for hook '{name}'")
    page = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>body{background:transparent;color:#e8eaed;"
        "font-family:'Segoe UI',system-ui,sans-serif;margin:0;padding:12px}"
        "</style></head><body>" + entry["html"] + "</body></html>"
    )
    return HTMLResponse(page)


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
            hook_infos.append(
                {
                    "name": info["name"],
                    "version": info["version"],
                    "display_name": info["display_name"],
                    "description": info["description"],
                    "author": info["author"],
                    "capabilities": info["capabilities"],
                    "plugin": info["plugin"],
                    "update_url": info["update_url"],
                    "source": info["source"],
                }
            )
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
        hook_infos.append(
            {
                "name": info["name"],
                "version": info["version"],
                "display_name": info["display_name"],
                "description": info["description"],
                "author": info["author"],
                "capabilities": info["capabilities"],
                "plugin": info["plugin"],
                "update_url": info["update_url"],
                "source": info["source"],
            }
        )

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


# ── Updates ───────────────────────────────────────────────────────────

_hook_updater = PackageUpdateChecker()


def _standalone_hooks_dir() -> Path:
    """Return the main hooks directory (standalone hooks only)."""
    dirs = discover_hooks_dirs()
    if not dirs:
        raise HTTPException(status_code=500, detail="Hooks directory not found")
    return dirs[0]


@router.get("/hooks/updates")
async def check_hook_updates():
    """Check all registered hooks for available updates.

    Same mechanism as ``GET /plugins/updates``: every hook with a
    non-empty ``update_url`` in its manifest is queried and its remote
    version compared against the registry version.  Hooks without an
    ``update_url`` are omitted.  Read-only.
    """
    registry = get_hook_registry()
    pkgs = [h.to_dict() for h in registry.list()]
    # Network-bound (one request per hook) → worker thread so the event
    # loop stays responsive while the check runs.
    results = await asyncio.to_thread(_hook_updater.check_updates, pkgs)
    updates_available = sum(1 for r in results if r.get("update_available"))
    return {
        "hooks": results,
        "total": len(results),
        "updates_available": updates_available,
    }


@router.post("/hooks/updates/install")
async def install_hook_updates():
    """Install all pending standalone hook updates.

    Only hooks that live directly in the main hooks directory can be
    updated here — plugin-bundled hooks follow their plugin's update
    cycle instead.  The user's ``config.yaml`` is preserved across an
    update; afterwards the running bridge should reload hooks (the
    dashboard restart flow does this implicitly).
    """
    registry = get_hook_registry()
    pkgs = {h.name: h.to_dict() for h in registry.list()}
    # Re-check to get latest versions (network-bound → worker thread)
    results = await asyncio.to_thread(_hook_updater.check_updates, list(pkgs.values()))

    hooks_dir = _standalone_hooks_dir()

    install_results: list[dict] = []
    for r in results:
        if not r.get("update_available"):
            continue
        name = r.get("name", "")
        display_name = r.get("display_name", name)
        latest_version = r.get("latest_version", "")
        if not name or not (hooks_dir / name).is_dir():
            install_results.append(
                {
                    "name": name,
                    "display_name": display_name,
                    "version": latest_version,
                    "success": False,
                    "error": "Not a standalone hook directory",
                }
            )
            continue
        pkg = dict(pkgs.get(name, {}))
        pkg["latest_version"] = latest_version
        # Download + extract are network/disk bound — keep them off the
        # event loop so SSE streams stay responsive.
        success = await asyncio.to_thread(_hook_updater.install_update, pkg, hooks_dir)
        if success:
            registry.update(name, version=latest_version)
        install_results.append(
            {
                "name": name,
                "display_name": display_name,
                "version": latest_version,
                "success": success,
                "error": None if success else "Installation failed",
            }
        )

    installed = sum(1 for r in install_results if r["success"])
    failed = sum(1 for r in install_results if not r["success"])
    return {"results": install_results, "installed": installed, "failed": failed}


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
    """Enable a hook. Takes effect immediately via runtime reload."""
    registry = get_hook_registry()
    hook = registry.get(name)
    if hook is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found")
    if hook.enabled:
        return {"status": "already_enabled", "name": name}
    registry.set_enabled(name, True)
    _invalidate_hook_cache()
    _request_hook_reload("enable", name)
    return {"status": "enabled", "name": name, "runtime_reload": "requested"}


@router.post("/hooks/{name}/disable")
async def disable_hook(name: str):
    """Disable a hook. Takes effect immediately via runtime reload."""
    registry = get_hook_registry()
    hook = registry.get(name)
    if hook is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found")
    if not hook.enabled:
        return {"status": "already_disabled", "name": name}
    registry.set_enabled(name, False)
    _invalidate_hook_cache()
    with _hook_widgets_lock:
        _hook_widgets.pop(name, None)
    _request_hook_reload("disable", name)
    return {"status": "disabled", "name": name, "runtime_reload": "requested"}


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
    """Update the per-hook config for a named hook.

    Triggers a runtime hook reload so the new config is read by the hook.
    """
    hook_dir = _find_hook_dir(name)
    if hook_dir is None:
        raise HTTPException(status_code=404, detail=f"Hook '{name}' not found on disk")

    new_config = body.get("config", {})
    try:
        save_plugin_config(hook_dir, new_config, backup=True)
    except (OSError, ValueError, YAMLError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {exc}")

    _request_hook_reload("config_change", name)
    return {"status": "saved", "name": name, "runtime_reload": "requested"}


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
