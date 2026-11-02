"""Built-in script action endpoints."""

from fastapi import APIRouter, HTTPException

from core.api.services import ApiService
from core.builtin_actions import get_config, list_builtins, set_config

router = APIRouter(prefix="/builtins", tags=["builtins"])

_api_service = None


def _get_api_service() -> ApiService:
    global _api_service
    if _api_service is None:
        _api_service = ApiService()
    return _api_service


@router.get("")
async def get_builtins():
    return {"builtins": list_builtins()}


@router.get("/{name}/config")
async def get_builtin_config(name: str):
    service = _get_api_service()
    try:
        cfg = service.read_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"config": get_config(cfg, name)}


@router.get("/{name}/config/schema")
async def get_builtin_config_schema(name: str):
    for b in list_builtins():
        if b["name"] == name:
            return {"config_schema": b.get("config_schema")}
    raise HTTPException(status_code=404, detail="Unknown builtin")


@router.put("/{name}/config")
async def put_builtin_config(name: str, body: dict):
    service = _get_api_service()
    try:
        cfg = service.read_config()
        set_config(cfg, name, body.get("config", body))
        service.write_config(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}
