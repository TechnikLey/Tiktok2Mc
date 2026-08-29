import logging

from fastapi import APIRouter, HTTPException

from core.api.models import ConfigResponse, ConfigUpdateRequest
from core.api.services import ApiService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Config"])

_service: ApiService | None = None


def _get_service() -> ApiService:
    global _service
    if _service is None:
        _service = ApiService()
    return _service


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    svc = _get_service()
    try:
        # Secrets are replaced with a placeholder; write_config strips it
        # again so GUI round-trips never overwrite the stored values.
        cfg = svc.get_config_redacted()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to read config")
        raise HTTPException(status_code=500, detail=str(e))
    return ConfigResponse(path=str(svc.config_path), config=cfg)


@router.put("/config", response_model=ConfigResponse)
async def update_config(body: ConfigUpdateRequest):
    svc = _get_service()
    try:
        svc.write_config(body.config, backup=body.backup)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to write config")
        raise HTTPException(status_code=500, detail=str(e))
    # Return the persisted state (normalised version, secrets redacted)
    # instead of echoing the request body.
    return ConfigResponse(path=str(svc.config_path), config=svc.get_config_redacted())
