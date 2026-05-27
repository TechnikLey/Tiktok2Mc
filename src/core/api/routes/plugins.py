from fastapi import APIRouter

from core.api.models import PluginInfo, PluginListResponse
from core.api.services import ApiService

router = APIRouter(tags=["Plugins"])
_service = ApiService()


@router.get("/plugins", response_model=PluginListResponse)
async def list_plugins():
    raw = _service.read_plugin_registry()
    infos = [
        PluginInfo(
            name=p.get("name", "unknown"),
            enabled=p.get("enable", False),
            level=p.get("level", 1),
            port=p.get("port", 0),
            ics=p.get("ics", False),
            path=p.get("path", ""),
        )
        for p in raw
    ]
    enabled_count = sum(1 for i in infos if i.enabled)
    return PluginListResponse(
        total=len(infos), enabled=enabled_count, plugins=infos
    )
