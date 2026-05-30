"""Plugin registration & management endpoints.

These replace the old file-based ``python.registry.register_plugin()``
flow.  Plugins now register via the API, which persists to its own
JSON store (``data/api_plugin_registry.json``).
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from core.api.models import (
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
from core.paths import get_root_dir

log = logging.getLogger(__name__)


def _write_plugin_signal(plugin_name: str, action: str) -> None:
    """Write a signal file that start.py watches for plugin lifecycle events."""
    runtime_dir = get_root_dir() / "core" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    signal_file = runtime_dir / f"plugin_{action}_{plugin_name}"
    try:
        signal_file.write_text(plugin_name, encoding="utf-8")
    except Exception as exc:
        log.warning("Failed to write plugin signal %s: %s", signal_file, exc)

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
        data = PluginRegistration(
            name=body.name,
            path=body.path,
            entry_point=body.entry_point,
            display_name=body.display_name,
            version=body.version,
            enabled=body.enabled,
            level=body.level,
            port=body.port,
            ics=body.ics,
            description=body.description,
            capabilities=body.capabilities,
            depends_on=body.depends_on,
            auto_enable=body.auto_enable,
            update_url=body.update_url,
            author=body.author,
            homepage=body.homepage,
        )
        result = registry.register(data)
        return PluginRegisterResponse(status="registered", plugin=result)
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

        plugins_dir = get_root_dir() / "plugins"
        if not plugins_dir.is_dir():
            plugins_dir = get_root_dir() / "src" / "plugins"
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
        plugins_dir = str(get_root_dir() / "src" / "plugins")
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
        result = registry.update(name, enabled=True)
        if result is None:
            log.error("Enable plugin '%s': registry.update returned None after get succeeded", name)
            raise HTTPException(
                status_code=500, detail=f"Registry inconsistency for plugin '{name}'"
            )
        _write_plugin_signal(name, "start")
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
        result = registry.update(name, enabled=False)
        if result is None:
            log.error("Disable plugin '%s': registry.update returned None after get succeeded", name)
            raise HTTPException(
                status_code=500, detail=f"Registry inconsistency for plugin '{name}'"
            )
        _write_plugin_signal(name, "stop")
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
    """Partially update a plugin's properties (e.g. enable/disable)."""
    try:
        registry = get_registry()
        result = registry.update(
            name,
            enabled=body.enabled,
            level=body.level,
            port=body.port,
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
        )
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
    """Remove a plugin from the registry."""
    try:
        registry = get_registry()
        if not registry.unregister(name):
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        return {"status": "unregistered", "name": name}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to unregister plugin")
        raise HTTPException(status_code=500, detail=str(e))


