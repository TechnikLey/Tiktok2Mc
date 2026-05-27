from fastapi import APIRouter

from .health import router as health_router
from .config import router as config_router
from .plugins import router as plugins_router
from .events import router as events_router
from .ws import router as ws_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(config_router)
api_router.include_router(plugins_router)
api_router.include_router(events_router)
api_router.include_router(ws_router)
