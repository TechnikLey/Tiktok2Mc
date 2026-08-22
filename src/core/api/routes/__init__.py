from fastapi import APIRouter

from .actions import router as actions_router
from .backups import router as backups_router
from .chatbot import router as chatbot_router
from .comment_commands import router as comment_commands_router
from .config import router as config_router
from .config_bundle import router as config_bundle_router
from .diagnostics import router as diagnostics_router
from .event_commands import router as event_commands_router
from .events import router as events_router
from .health import router as health_router
from .hooks import router as hooks_router
from .logs import router as logs_router
from .mc_plugins import router as mc_plugins_router
from .outbound import router as outbound_router
from .overlay import router as overlay_router
from .plugin_config import router as plugin_config_router
from .plugin_data import router as plugin_data_router
from .plugin_overlay import router as plugin_overlay_router
from .plugins import router as plugins_router
from .rcon import router as rcon_router
from .reactions import router as reactions_router
from .reload import router as reload_router
from .revenue import router as revenue_router
from .server_lifecycle import router as server_lifecycle_router
from .servers import router as servers_router
from .sessions import router as sessions_router
from .system import router as system_router
from .triggers import router as triggers_router
from .updater import router as updater_router
from .versions import router as versions_router
from .ws import router as ws_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(diagnostics_router)
api_router.include_router(config_router)
api_router.include_router(config_bundle_router)
api_router.include_router(sessions_router)
api_router.include_router(plugins_router)
api_router.include_router(plugin_config_router)
api_router.include_router(plugin_data_router)
api_router.include_router(events_router)
api_router.include_router(ws_router)
api_router.include_router(updater_router)
api_router.include_router(system_router)
api_router.include_router(reload_router)
api_router.include_router(actions_router)
api_router.include_router(backups_router)
api_router.include_router(overlay_router)
api_router.include_router(outbound_router)
api_router.include_router(plugin_overlay_router)
api_router.include_router(hooks_router)
api_router.include_router(event_commands_router)
api_router.include_router(comment_commands_router)
api_router.include_router(chatbot_router)
api_router.include_router(rcon_router)
api_router.include_router(reactions_router)
api_router.include_router(revenue_router)
api_router.include_router(versions_router)
api_router.include_router(triggers_router)
api_router.include_router(logs_router)
api_router.include_router(mc_plugins_router)
api_router.include_router(servers_router)
api_router.include_router(server_lifecycle_router)
