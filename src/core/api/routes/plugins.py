"""Plugin registration & management endpoints.

These replace the old file-based ``python.registry.register_plugin()``
flow.  Plugins now register via the API, which persists to its own
JSON store (``data/api_plugin_registry.json``).
"""

import logging

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
)
from core.api.registry import get_registry
from core.api.updater import PluginUpdateChecker

log = logging.getLogger(__name__)

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


# ── Enable / Disable ─────────────────────────────────────────────────


@router.post("/plugins/{name}/enable", response_model=PluginRegistration)
async def enable_plugin(name: str):
    """Enable a plugin by name."""
    try:
        registry = get_registry()
        result = registry.update(name, enabled=True)
        if result is None:
            raise HTTPException(
                status_code=404, detail=f"Plugin '{name}' not found"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to enable plugin")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/plugins/{name}/disable", response_model=PluginRegistration)
async def disable_plugin(name: str):
    """Disable a plugin by name."""
    try:
        registry = get_registry()
        result = registry.update(name, enabled=False)
        if result is None:
            raise HTTPException(
                status_code=404, detail=f"Plugin '{name}' not found"
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to disable plugin")
        raise HTTPException(status_code=500, detail=str(e))


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


