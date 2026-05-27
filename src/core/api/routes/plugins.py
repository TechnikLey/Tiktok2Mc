"""Plugin registration & management endpoints.

These replace the old file-based ``python.registry.register_plugin()``
flow.  Plugins now register via the API, which persists to its own
JSON store (``data/api_plugin_registry.json``).
"""

from fastapi import APIRouter, HTTPException

from core.api.models import (
    PluginListResponse,
    PluginRegisterRequest,
    PluginRegisterResponse,
    PluginRegistration,
    PluginUpdateRequest,
)
from core.api.registry import get_registry

router = APIRouter(tags=["Plugins"])


# ── Register ─────────────────────────────────────────────────────────


@router.post(
    "/plugins/register",
    response_model=PluginRegisterResponse,
    status_code=201,
)
async def register_plugin(body: PluginRegisterRequest):
    """Register or update a plugin in the central registry."""
    registry = get_registry()
    data = PluginRegistration(
        name=body.name,
        path=body.path,
        version=body.version,
        enabled=body.enabled,
        level=body.level,
        port=body.port,
        ics=body.ics,
        description=body.description,
    )
    result = registry.register(data)
    return PluginRegisterResponse(status="registered", plugin=result)


# ── List ─────────────────────────────────────────────────────────────


@router.get("/plugins", response_model=PluginListResponse)
async def list_plugins():
    """Return every registered plugin."""
    registry = get_registry()
    plugins = registry.list()
    enabled = sum(1 for p in plugins if p.enabled)
    return PluginListResponse(
        total=len(plugins), enabled=enabled, plugins=plugins
    )


# ── Get single ───────────────────────────────────────────────────────


@router.get("/plugins/{name}", response_model=PluginRegistration)
async def get_plugin(name: str):
    """Return a single plugin by name."""
    registry = get_registry()
    plugin = registry.get(name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return plugin


# ── Update ────────────────────────────────────────────────────────────


@router.put("/plugins/{name}", response_model=PluginRegistration)
async def update_plugin(name: str, body: PluginUpdateRequest):
    """Partially update a plugin's properties (e.g. enable/disable)."""
    registry = get_registry()
    plugin = registry.get(name)
    if plugin is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    result = registry.update(
        name,
        enabled=body.enabled,
        level=body.level,
        port=body.port,
        ics=body.ics,
        path=body.path,
        version=body.version,
        description=body.description,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return result


# ── Unregister ───────────────────────────────────────────────────────


@router.delete("/plugins/{name}")
async def unregister_plugin(name: str):
    """Remove a plugin from the registry."""
    registry = get_registry()
    if not registry.unregister(name):
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    return {"status": "unregistered", "name": name}


# ── Import legacy ────────────────────────────────────────────────────
# The ``POST /plugins/import-legacy`` endpoint has been removed.
# Legacy PLUGIN_REGISTRY.json is no longer supported.
