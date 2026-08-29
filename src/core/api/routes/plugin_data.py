"""Namespaced persistence endpoints for plugins and hooks.

All paths live under ``/api/v1``.  The namespace is the extension name
(``{name}``); keys are flat strings, values arbitrary JSON.

Thin routes only — storage logic lives in
``core.api.services.persistence_service``.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.services.persistence_service import (
    PersistenceError,
    get_persistence_service,
)

router = APIRouter(tags=["Plugin Data"])


class PluginDataSetRequest(BaseModel):
    value: Any


@router.get("/plugins/{name}/data")
async def get_plugin_data(name: str):
    """Return the whole key/value store of a plugin or hook."""
    try:
        return {"name": name, "data": get_persistence_service().get_store(name)}
    except PersistenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/plugins/{name}/data/{key}")
async def get_plugin_data_key(name: str, key: str):
    """Return a single value from the plugin's store (404 when absent)."""
    try:
        found, value = get_persistence_service().get(name, key)
    except PersistenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not found:
        raise HTTPException(
            status_code=404, detail=f"Key '{key}' not found for '{name}'"
        )
    return {"name": name, "key": key, "value": value}


@router.put("/plugins/{name}/data/{key}")
async def set_plugin_data_key(name: str, key: str, body: PluginDataSetRequest):
    """Create or overwrite ``key`` with an arbitrary JSON value."""
    try:
        get_persistence_service().set(name, key, body.value)
    except PersistenceError as exc:
        status = 422 if "match" in str(exc) else 500
        raise HTTPException(status_code=status, detail=str(exc))
    return {"name": name, "key": key, "value": body.value}


@router.delete("/plugins/{name}/data/{key}")
async def delete_plugin_data_key(name: str, key: str):
    """Delete ``key``; 404 when it did not exist."""
    try:
        deleted = get_persistence_service().delete(name, key)
    except PersistenceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Key '{key}' not found for '{name}'"
        )
    return {"name": name, "key": key, "deleted": True}
