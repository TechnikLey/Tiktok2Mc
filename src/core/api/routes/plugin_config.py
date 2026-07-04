from fastapi import APIRouter, HTTPException
from typing import Any

from copy import deepcopy

from core.plugin_config import (
    _FRAMEWORK_FIELDS,
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
                detail=f"Validation failed: {errors}",
            )

    backup = body.pop("_backup", True)
    try:
        save_plugin_config(plugin_dir, body, backup=backup)
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

        # Inject framework-managed fields into the schema response so the
        # GUI always renders them regardless of the plugin's own schema
        if schema is None:
            schema = {"fields": []}
        else:
            schema = deepcopy(schema)
            schema.setdefault("fields", [])

        existing_keys = {f.get("key") for f in schema["fields"]}
        for fname in _FRAMEWORK_FIELDS:
            if fname not in existing_keys:
                schema["fields"].insert(
                    0,
                    {
                        "key": fname,
                        "type": "boolean",
                        "label": "Enable Plugin",
                        "section": "General",
                        "default": True,
                        "framework": True,
                    },
                )
            elif not any(f.get("framework") for f in schema["fields"] if f.get("key") == fname):
                # Mark existing enabled field as framework-managed
                for f in schema["fields"]:
                    if f.get("key") == fname:
                        f["framework"] = True
                        f["default"] = True
                        break

        return {"name": name, "schema": schema}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
