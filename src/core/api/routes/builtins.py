"""Built-in script action endpoints."""

from fastapi import APIRouter, HTTPException

from core.api.services import ApiService
from core.builtin_actions import get_config, list_builtins, set_config

router = APIRouter(prefix="/builtins", tags=["builtins"])

_api_service = None


def _get_api_service() -> ApiService:
    """Return the lazily created module-level `ApiService` instance."""
    global _api_service
    if _api_service is None:
        _api_service = ApiService()
    return _api_service


@router.get("")
async def get_builtins():
    """List all built-in script actions and their metadata."""
    return {"builtins": list_builtins()}


@router.get("/{name}/config")
async def get_builtin_config(name: str):
    """Return the stored configuration for one built-in action.

Args:
    name: Built-in action name as reported by `list_builtins`.

Returns:
    A JSON object with the action's configuration under ``config``.

Raises:
    HTTPException: 500 if the configuration cannot be read."""

    service = _get_api_service()
    try:
        cfg = service.read_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"config": get_config(cfg, name)}


@router.get("/{name}/config/schema")
async def get_builtin_config_schema(name: str):
    """Return the configuration schema declared by a built-in action.

Args:
    name: Built-in action name.

Raises:
    HTTPException: 404 if no built-in action with that name exists."""

    for b in list_builtins():
        if b["name"] == name:
            return {"config_schema": b.get("config_schema")}
    raise HTTPException(status_code=404, detail="Unknown builtin")


@router.put("/{name}/config")
async def put_builtin_config(name: str, body: dict):
    """Replace the configuration of a built-in action.

Args:
    name: Built-in action name.
    body: Either the configuration mapping itself or an object with a
        ``config`` key containing it.

Returns:
    ``{"ok": True}`` after the configuration has been persisted.

Raises:
    HTTPException: 500 if the configuration cannot be read or written."""

    service = _get_api_service()
    try:
        cfg = service.read_config()
        set_config(cfg, name, body.get("config", body))
        service.write_config(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}
