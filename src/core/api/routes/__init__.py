from fastapi import APIRouter

from .health import router as health_router
from .config import router as config_router
from .plugins import router as plugins_router
from .plugin_config import router as plugin_config_router
from .events import router as events_router
from .ws import router as ws_router
from .updater import router as updater_router
from .system import router as system_router
from .reload import router as reload_router
from .actions import router as actions_router
from .plugin_overlay import router as plugin_overlay_router
from .overlay import router as overlay_router
from .hooks import router as hooks_router
from .event_commands import router as event_commands_router
from .rcon import router as rcon_router
from .versions import router as versions_router
from .triggers import router as triggers_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(config_router)
api_router.include_router(plugins_router)
api_router.include_router(plugin_config_router)
api_router.include_router(events_router)
api_router.include_router(ws_router)
api_router.include_router(updater_router)
api_router.include_router(system_router)
api_router.include_router(reload_router)
api_router.include_router(actions_router)
api_router.include_router(overlay_router)
api_router.include_router(plugin_overlay_router)
api_router.include_router(hooks_router)
api_router.include_router(event_commands_router)
api_router.include_router(rcon_router)
api_router.include_router(versions_router)
api_router.include_router(triggers_router)
