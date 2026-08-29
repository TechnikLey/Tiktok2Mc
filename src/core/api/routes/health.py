import logging

from fastapi import APIRouter, HTTPException

from core.api.models import (
    API_VERSION,
    TOOL_VERSION,
    HealthResponse,
    StatusDetail,
)
from core.api.registry import get_registry
from core.api.services import ApiService
from core.api.services.bridge_metrics import get_bridge_metrics_service
from core.api.tiktok_live import get_tiktok_live_tracker
from core.health_monitor import get_health_monitor

log = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])
_service: ApiService | None = None


def _get_service() -> ApiService:
    global _service
    if _service is None:
        _service = ApiService()
    return _service


@router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        api_version=API_VERSION,
        tool_version=TOOL_VERSION,
    )


@router.get("/status", response_model=StatusDetail)
async def status():
    try:
        plugins = get_registry().list()
        enabled = sum(1 for p in plugins if p.enabled)
        tracker = get_tiktok_live_tracker().snapshot()

        # Fetch bridge metrics (non-blocking, best effort)
        bridge_metrics = {}
        try:
            bridge_metrics = await get_bridge_metrics_service().get_metrics()
        except Exception as e:
            log.debug("Failed to fetch bridge metrics: %s", e)

        return StatusDetail(
            server="running",
            plugins_active=enabled,
            plugins_total=len(plugins),
            config_loaded=_get_service().get_config_status(),
            uptime_seconds=_get_service().get_uptime(),
            tiktok_live=tracker.get("tiktok_live"),
            tiktok_live_last_update=tracker.get("tiktok_live_last_update"),
            tiktok_live_last_event=tracker.get("tiktok_live_last_event"),
            tiktok_live_source=tracker.get("tiktok_live_source", ""),
            rcon_queue_size=bridge_metrics.get("rcon_queue_size"),
            trigger_queue_size=bridge_metrics.get("trigger_queue_size"),
            events_per_minute=bridge_metrics.get("events_per_minute"),
            gift_value_usd_today=bridge_metrics.get("gift_value_usd_today"),
        )
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to get status")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health/extended")
async def health_extended():
    """Extended health check with subsystem status."""
    try:
        plugins = get_registry().list()
        enabled = sum(1 for p in plugins if p.enabled)
        global_health = get_health_monitor()

        return {
            "status": "ok",
            "version": API_VERSION,
            "api_version": API_VERSION,
            "tool_version": TOOL_VERSION,
            "plugins": {
                "active": enabled,
                "total": len(plugins),
            },
            "config_loaded": _get_service().get_config_status(),
            "uptime_seconds": _get_service().get_uptime(),
            "subsystems": global_health.summary(),
        }
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to get extended health")
        raise HTTPException(status_code=500, detail=str(e))
