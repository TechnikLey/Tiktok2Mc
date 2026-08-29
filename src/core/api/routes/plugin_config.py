from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from ruamel.yaml.error import YAMLError

from core.plugin_config import (
    discover_plugins_dir,
    load_plugin_config,
    load_plugin_manifest,
    save_plugin_config,
    validate_plugin_config,
)

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
    except (OSError, ValueError, YAMLError) as e:
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
    except (OSError, ValueError, YAMLError) as e:
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

        if schema is None:
            schema = {"fields": []}

        return {"name": name, "schema": schema}
    except Exception as e:  # any unexpected error becomes an HTTP 500
        raise HTTPException(status_code=500, detail=str(e))


# ── README ────────────────────────────────────────────────────────────


@router.get("/plugins/{name}/readme")
async def get_plugin_readme(name: str):
    """Return the plugin's README.md as Markdown text."""
    plugin_dir = _find_plugin_dir(name)
    if not plugin_dir:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    readme_path = plugin_dir / "README.md"
    if not readme_path.is_file():
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' has no README.md")
    try:
        md = readme_path.read_text(encoding="utf-8")
        return PlainTextResponse(md, media_type="text/markdown")
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
