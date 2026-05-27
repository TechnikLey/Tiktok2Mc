from fastapi import APIRouter

from core.api.models import HealthResponse, StatusDetail
from core.api.services import ApiService

router = APIRouter(tags=["Health"])
_service = ApiService()


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok", version="0.5.0", api_version="1.0.0"
    )


@router.get("/status", response_model=StatusDetail)
async def status():
    plugins = _service.read_plugin_registry()
    enabled = sum(1 for p in plugins if p.get("enable", False))
    return StatusDetail(
        server="running",
        plugins_active=enabled,
        plugins_total=len(plugins),
        config_loaded=_service.get_config_status(),
        uptime_seconds=_service.get_uptime(),
    )
