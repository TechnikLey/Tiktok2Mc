from fastapi import APIRouter, HTTPException
from typing import Any

from core.plugin_config import (
    discover_plugins_dir,
    load_plugin_manifest,
    load_plugin_config,
    save_plugin_config,
    validate_plugin_config,
)
from core.api.models import ConfigResponse

router = APIRouter(tags=["Plugin Config"])


def _find_plugin_dir(name: str):
    """Locate a plugin directory by its manifest ``name``."""
    plugins_dir = discover_plugins_dir()
    for child in plugins_dir.iterdir():
        if not child.is_dir():
            continue
        manifest = load_plugin_manifest(child)
        if manifest and manifest.get("name") == name:
            return child
    return None


@router.get("/plugins/{name}/config")
async def get_plugin_config(name: str):
    """Return the current local config for a plugin."""
    plugin_dir = _find_plugin_dir(name)
    if not plugin_dir:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    try:
        cfg = load_plugin_config(plugin_dir)
        return {"name": name, "config": cfg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/plugins/{name}/config")
async def update_plugin_config(name: str, body: dict[str, Any]):
    """Validate and write a plugin's local ``config.yaml``."""
    plugin_dir = _find_plugin_dir(name)
    if not plugin_dir:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")

    manifest = load_plugin_manifest(plugin_dir)
    schema = manifest.get("config_schema") if manifest else None
    if schema:
        errors = validate_plugin_config(body, schema)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Validation failed", "errors": errors},
            )

    try:
        save_plugin_config(plugin_dir, body)
        return {"name": name, "config": body}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plugins/{name}/config/schema")
async def get_plugin_schema(name: str):
    """Return the ``config_schema`` declared by a plugin (or ``null``)."""
    plugin_dir = _find_plugin_dir(name)
    if not plugin_dir:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    try:
        manifest = load_plugin_manifest(plugin_dir)
        schema = manifest.get("config_schema") if manifest else None
        return {"name": name, "schema": schema}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
