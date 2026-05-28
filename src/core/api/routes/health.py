import logging

from fastapi import APIRouter, HTTPException

from core.api.models import API_VERSION, HealthResponse, StatusDetail
from core.api.services import ApiService
from core.api.registry import get_registry

log = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])
_service = ApiService()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok", version=API_VERSION, api_version=API_VERSION
    )


@router.get("/status", response_model=StatusDetail)
async def status():
    try:
        plugins = get_registry().list()
        enabled = sum(1 for p in plugins if p.enabled)
        return StatusDetail(
            server="running",
            plugins_active=enabled,
            plugins_total=len(plugins),
            config_loaded=_service.get_config_status(),
            uptime_seconds=_service.get_uptime(),
        )
    except Exception as e:
        log.exception("Failed to get status")
        raise HTTPException(status_code=500, detail=str(e))
