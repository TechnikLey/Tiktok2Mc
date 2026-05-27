from fastapi import APIRouter, HTTPException

from core.api.models import ConfigResponse, ConfigUpdateRequest
from core.api.services import ApiService

router = APIRouter(tags=["Config"])
_service = ApiService()


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    try:
        cfg = _service.read_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ConfigResponse(path=str(_service.config_path), config=cfg)


@router.put("/config", response_model=ConfigResponse)
async def update_config(body: ConfigUpdateRequest):
    try:
        _service.write_config(body.config, backup=body.backup)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ConfigResponse(path=str(_service.config_path), config=body.config)
