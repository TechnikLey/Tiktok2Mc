"""Plugin registration & management endpoints.

These replace the old file-based ``python.registry.register_plugin()``
flow.  Plugins now register via the API, which persists to its own
JSON store (``data/api_plugin_registry.json``).
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from core.api.dependency import validate_dependencies
from core.api.models import (
    CommentHandler,
    PluginListResponse,
    PluginRegisterRequest,
    PluginRegisterResponse,
    PluginRegistration,
    PluginUpdatesResponse,
    PluginUpdateStatus,
    PluginUpdateRequest,
    PluginUpdatesInstallResponse,
    PluginUpdateInstallResult,
)
from core.api.registry import get_registry
from core.api.services.plugin_discovery import discover_plugins_from_manifests
from core.api.updater import PluginUpdateChecker
import core.paths

log = logging.getLogger(__name__)

_HEALTH_POLL_TIMEOUT = 30.0


def _runtime_dir() -> Path:
    d = core.paths.get_root_dir() / "core" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_plugin_signal(plugin_name: str, action: str) -> bool:
    """Write a signal file that start.py watches for plugin lifecycle events.
    
    Returns ``True`` if the signal was written successfully.
    """
    signal_file = _runtime_dir() / f"plugin_{action}_{plugin_name}"
    try:
        signal_file.write_text(plugin_name, encoding="utf-8")
        return True
    except Exception as exc:
        log.warning("Failed to write plugin signal %s: %s", signal_file, exc)
        return False


def _clean_plugin_signals(plugin_name: str) -> None:
    """Remove all runtime signal files for a plugin."""
    rd = _runtime_dir()
    for pattern in (f"plugin_start_{plugin_name}", f"plugin_stop_{plugin_name}"):
        p = rd / pattern
        try:
            if p.exists():
                p.unlink()
        except Exception as exc:
            log.warning("Failed to clean signal %s: %s", p, exc)


router = APIRouter(tags=["Plugins"])


# ── Register ─────────────────────────────────────────────────────────


@router.post(
    "/plugins/register",
    response_model=PluginRegisterResponse,
    status_code=201,
)
async def register_plugin(body: PluginRegisterRequest):
    """Register or update a plugin in the central registry."""
    try:
        registry = get_registry()
        if body.depends_on:
            registered = {p.name: p for p in registry.list()}
            missing = validate_dependencies(body.name, body.depends_on, registered)
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=f"Plugin '{body.name}' depends on unregistered plugin(s): {', '.join(missing)}",
                )
        data = PluginRegistration(
            name=body.name,
            path=body.path,
            entry_point=body.entry_point,
            display_name=body.display_name,
            version=body.version,
            enabled=body.enabled,
            level=body.level,
            ics=body.ics,
            description=body.description,
            capabilities=body.capabilities,
            depends_on=body.depends_on,
            auto_enable=body.auto_enable,
            update_url=body.update_url,
            author=body.author,
            homepage=body.homepage,
            comment_handler=body.comment_handler,
        )
        result = registry.register(data)
        return PluginRegisterResponse(status="registered", plugin=result)
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        log.exception("Failed to register plugin")
        raise HTTPException(status_code=500, detail=str(e))


# ── List ─────────────────────────────────────────────────────────────


@router.get("/plugins", response_model=PluginListResponse)
async def list_plugins():
    """Return every registered plugin."""
    try:
        registry = get_registry()
        plugins = registry.list()
        enabled = sum(1 for p in plugins if p.enabled)
        return PluginListResponse(
            total=len(plugins), enabled=enabled, plugins=plugins
        )
    except Exception as e:
        log.exception("Failed to list plugins")
        raise HTTPException(status_code=500, detail=str(e))


# ── Updates ──────────────────────────────────────────────────────────

_updater = PluginUpdateChecker()


@router.get("/plugins/updates", response_model=PluginUpdatesResponse)
async def check_plugin_updates():
    """Check all registered plugins for available updates."""
    try:
        registry = get_registry()
        plugins = [p.model_dump(mode="json") for p in registry.list()]
        results = _updater.check_updates(plugins)
        updates_available = sum(
            1 for r in results if r.get("update_available")
        )
        return PluginUpdatesResponse(
            plugins=[PluginUpdateStatus(**r) for r in results],
            total=len(results),
            updates_available=updates_available,
        )
    except Exception as e:
        log.exception("Failed to check plugin updates")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plugins/updates/install", response_model=PluginUpdatesInstallResponse)
async def install_plugin_updates():
    """Install all pending plugin updates immediately."""
    try:
        registry = get_registry()
        plugins = [p.model_dump(mode="json") for p in registry.list()]
        # Re-check to get latest versions
        results = _updater.check_updates(plugins)

        plugins_dir = core.paths.get_root_dir() / "plugins"
        if not plugins_dir.is_dir():
            plugins_dir = core.paths.get_root_dir() / "src" / "plugins"
        if not plugins_dir.is_dir():
            raise HTTPException(status_code=500, detail="Cannot locate plugins directory")

        install_results: list[PluginUpdateInstallResult] = []
        for r in results:
            if not r.get("update_available"):
                continue
            name = r.get("name", "")
            display_name = r.get("display_name", name)
            latest_version = r.get("latest_version", "")
            plugin = next((p for p in plugins if p.get("name") == name), {})
            success = _updater.install_update(plugin, plugins_dir)
            if success:
                # Update registry with new version
                registry.update(name, version=latest_version)
            install_results.append(
                PluginUpdateInstallResult(
                    name=name,
                    display_name=display_name,
                    version=latest_version,
                    success=success,
                    error=None if success else "Installation failed",
                )
            )

        installed = sum(1 for r in install_results if r.success)
        failed = sum(1 for r in install_results if not r.success)
        return PluginUpdatesInstallResponse(
            results=install_results, installed=installed, failed=failed
        )
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to install plugin updates")
        raise HTTPException(status_code=500, detail=str(e))


# ── Discover ──────────────────────────────────────────────────────────


@router.get("/plugins/discover")
async def discover_plugins():
    """Scan filesystem manifests and merge with registry state.

    Returns every plugin found in ``src/plugins/*/plugin.json`` with
    its current ``enabled`` state from the registry.

    This is a **read-only** operation — no plugins are registered
    or loaded as a side effect.
    """
    try:
        plugins_dir = str(core.paths.get_root_dir() / "src" / "plugins")
        discovered = discover_plugins_from_manifests(plugins_dir)
    except Exception as e:
        log.exception("Failed to discover plugins")
        raise HTTPException(status_code=500, detail=str(e))

    # Merge registry state (read-only query, no side effects)
    try:
        registry = get_registry()
        registry_plugins = {p.name: p for p in registry.list()}
    except Exception:
        registry_plugins = {}

    for entry in discovered:
        reg = registry_plugins.get(entry["name"])
        entry["enabled"] = reg.enabled if reg is not None else False
        entry.pop("enabled_by_registry", None)

    return {"plugins": discovered}


# ── Enable / Disable ─────────────────────────────────────────────────


@router.post("/plugins/{name}/enable", response_model=PluginRegistration)
async def enable_plugin(name: str):
    """Enable a plugin by name and signal runtime start."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if plugin is None:
            log.warning("Enable plugin '%s' failed: not found in registry", name)
            raise HTTPException(
                status_code=404, detail=f"Plugin '{name}' not found in registry"
            )
        if plugin.enabled:
            log.info("Plugin '%s' is already enabled — returning current state", name)
            return plugin
        # Check dependencies are enabled
        if plugin.depends_on:
            registered = {p.name: p for p in registry.list()}
            for dep_name in plugin.depends_on:
                dep = registered.get(dep_name)
                if dep is None:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Cannot enable '{name}': dependency '{dep_name}' is not registered",
                    )
                if not dep.enabled:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Cannot enable '{name}': dependency '{dep_name}' is not enabled",
                    )
        # Write signal FIRST so start.py sees it immediately
        if not _write_plugin_signal(name, "start"):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write start signal for plugin '{name}'",
            )
        # Only update registry after signal was written successfully
        result = registry.update(name, enabled=True, health_status="healthy")
        if result is None:
            log.error("Enable plugin '%s': registry.update returned None after get succeeded", name)
            raise HTTPException(
                status_code=500, detail=f"Registry inconsistency for plugin '{name}'"
            )
        log.info("Plugin '%s' enabled and start signal written", name)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to enable plugin '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=f"Failed to enable plugin '{name}': {e}")


@router.post("/plugins/{name}/disable", response_model=PluginRegistration)
async def disable_plugin(name: str):
    """Disable a plugin by name and signal runtime stop."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if plugin is None:
            log.warning("Disable plugin '%s' failed: not found in registry", name)
            raise HTTPException(
                status_code=404, detail=f"Plugin '{name}' not found in registry"
            )
        if not plugin.enabled:
            log.info("Plugin '%s' is already disabled — returning current state", name)
            return plugin
        # Write signal FIRST so start.py sees it immediately
        if not _write_plugin_signal(name, "stop"):
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write stop signal for plugin '{name}'",
            )
        # Only update registry after signal was written successfully
        result = registry.update(name, enabled=False, health_status="unknown")
        if result is None:
            log.error("Disable plugin '%s': registry.update returned None after get succeeded", name)
            raise HTTPException(
                status_code=500, detail=f"Registry inconsistency for plugin '{name}'"
            )
        log.info("Plugin '%s' disabled and stop signal written", name)
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to disable plugin '%s': %s", name, e)
        raise HTTPException(status_code=500, detail=f"Failed to disable plugin '{name}': {e}")


# ── Get single ───────────────────────────────────────────────────────


@router.get("/plugins/{name}", response_model=PluginRegistration)
async def get_plugin(name: str):
    """Return a single plugin by name."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        return plugin
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to get plugin")
        raise HTTPException(status_code=500, detail=str(e))


# ── Update ────────────────────────────────────────────────────────────


@router.put("/plugins/{name}", response_model=PluginRegistration)
async def update_plugin(name: str, body: PluginUpdateRequest):
    """Partially update a plugin's properties (e.g. enable/disable, health)."""
    try:
        registry = get_registry()
        # Validate depends_on if being updated
        if body.depends_on is not None:
            registered = {p.name: p for p in registry.list()}
            missing = validate_dependencies(name, body.depends_on, registered)
            if missing:
                raise HTTPException(
                    status_code=422,
                    detail=f"Plugin '{name}' depends on unregistered plugin(s): {', '.join(missing)}",
                )
        kwargs: dict[str, Any] = dict(
            enabled=body.enabled,
            level=body.level,
            ics=body.ics,
            path=body.path,
            version=body.version,
            description=body.description,
            entry_point=body.entry_point,
            display_name=body.display_name,
            capabilities=body.capabilities,
            depends_on=body.depends_on,
            auto_enable=body.auto_enable,
            update_url=body.update_url,
            author=body.author,
            homepage=body.homepage,
            health_status=body.health_status,
            last_heartbeat=body.last_heartbeat,
        )
        # Strip None values so registry.update only touches provided fields
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        result = registry.update(name, **kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to update plugin")
        raise HTTPException(status_code=500, detail=str(e))


# ── Unregister ───────────────────────────────────────────────────────


@router.delete("/plugins/{name}")
async def unregister_plugin(name: str):
    """Remove a plugin from the registry, stop its process, and clean up signals."""
    try:
        # 1. Write stop signal so start.py terminates the running process
        _write_plugin_signal(name, "stop")
        _clean_plugin_signals(name)

        # 2. Remove from registry
        registry = get_registry()
        if not registry.unregister(name):
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

        log.info("Plugin '%s' unregistered, process stopped, signals cleaned", name)
        return {"status": "unregistered", "name": name}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to unregister plugin")
        raise HTTPException(status_code=500, detail=str(e))


# ── Comment Handlers ─────────────────────────────────────────────────


@router.put("/plugins/{name}/comment-handler")
async def set_comment_handler(name: str, body: CommentHandler):
    """Register or update a plugin's comment handler."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        plugin.comment_handler = body
        registry.update(name, {"comment_handler": body})
        log.info("Comment handler for '%s': prefix=%s", name, body.prefix)
        return {"status": "updated", "plugin": name, "handler": body.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to set comment handler")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/plugins/{name}/comment-handler")
async def remove_comment_handler(name: str):
    """Remove a plugin's comment handler."""
    try:
        registry = get_registry()
        plugin = registry.get(name)
        if not plugin:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        plugin.comment_handler = None
        registry.update(name, {"comment_handler": None})
        log.info("Comment handler removed for '%s'", name)
        return {"status": "removed", "plugin": name}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to remove comment handler")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comment-handlers")
async def list_comment_handlers():
    """Return all registered comment handlers as ``{prefix: plugin_name}``."""
    try:
        registry = get_registry()
        handlers: dict[str, str] = {}
        for plugin in registry.list():
            ch = plugin.comment_handler
            if ch and ch.enabled:
                handlers[ch.prefix] = plugin.name
        return {"handlers": handlers}
    except Exception as e:
        log.exception("Failed to list comment handlers")
        raise HTTPException(status_code=500, detail=str(e))


