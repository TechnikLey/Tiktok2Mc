import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.status import HTTP_401_UNAUTHORIZED

from fastapi.staticfiles import StaticFiles

from .routes import api_router
from .eventbus import event_bus
from .models import API_VERSION
from .plugin_health import get_health_monitor
from .plugin_watcher import get_plugin_watcher
from .plugin_overlay import command_queue
from .dashboard_publisher import get_dashboard_publisher
from .services.rcon import get_rcon_service
from .services import ApiService
from core.paths import get_root_dir
from core.overlay import set_event_loop

log = logging.getLogger(__name__)

DEFAULT_PORT = 29185

_LOCALHOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.event_command_mapper import get_event_command_mapper

    log.info("API server v%s starting up ...", API_VERSION)
    log.info(
        "CORS origin restricted to localhost — "
        "use create_app(cors_origins=[\"*\"]) to open for development"
    )
    set_event_loop(asyncio.get_running_loop())
    command_queue.set_loop(asyncio.get_running_loop())
    get_plugin_watcher().start()
    await get_health_monitor().start()
    get_event_command_mapper().start()
    get_dashboard_publisher().start()
    # Pre-configure RCON from config for the console feature
    try:
        cfg = ApiService().read_config()
        rcon_cfg = cfg.get("rcon", {})
        get_rcon_service().configure(
            host=rcon_cfg.get("host", "localhost"),
            port=rcon_cfg.get("port", 25575),
            password=rcon_cfg.get("password", ""),
        )
    except Exception:
        log.warning("Could not read RCON config — console will auto-configure on first request")

    await event_bus.publish("server.started", {"version": API_VERSION})
    try:
        yield
    except asyncio.CancelledError:
        # Expected when the supervisor cancels the API server task during shutdown.
        pass
    finally:
        await get_rcon_service().disconnect()
        await get_dashboard_publisher().stop()
        await get_event_command_mapper().stop()
        await get_health_monitor().stop()
        await event_bus.publish("server.stopping", {})
        log.info("API server shutting down ...")


def create_app(
    title: str = "TikTok2MC API",
    version: str = API_VERSION,
    cors_origins: list[str] | None = None,
    api_key: str = "",
) -> FastAPI:
    """Build and return a configured FastAPI application instance.

    Parameters
    ----------
    title:
        Application title shown in the OpenAPI docs.
    version:
        API version string.
    cors_origins:
        List of allowed origins for CORS.  Defaults to ``["*"]``.
    api_key:
        Optional API key for authentication.  When set, all non-localhost
        requests must include the ``X-API-Key`` header.  Empty means
        authentication is disabled.

    Returns
    -------
    FastAPI
        Ready-to-serve application.
    """
    app = FastAPI(
        title=title,
        version=version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or [
            "http://127.0.0.1",
            "http://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class CancelledErrorMiddleware(BaseHTTPMiddleware):
        """Suppress CancelledError spam when clients disconnect or the server shuts down."""
        async def dispatch(self, request, call_next):
            try:
                return await call_next(request)
            except asyncio.CancelledError:
                return Response(status_code=499)

    app.add_middleware(CancelledErrorMiddleware)

    app.include_router(api_router)

    if api_key:
        @app.middleware("http")
        async def check_api_key(request: Request, call_next):
            client_host = request.client.host if request.client else ""

            if client_host not in _LOCALHOSTS:
                req_key = request.headers.get("X-API-Key", "")
                if req_key != api_key:
                    return JSONResponse(
                        {"detail": "Missing or invalid API key. Provide X-API-Key header."},
                        status_code=HTTP_401_UNAUTHORIZED,
                    )
            return await call_next(request)

    # Serve the central GUI dashboard at /gui
    # Release layout: core/templates/gui/   Dev layout: templates/gui/
    root = get_root_dir()
    gui_dir = root / "core" / "templates" / "gui"
    if not gui_dir.exists():
        gui_dir = root / "templates" / "gui"
    if gui_dir.exists():
        app.mount(
            "/gui",
            StaticFiles(directory=str(gui_dir), html=True),
            name="gui",
        )

    # Serve gift images at /gifts-pictures
    # Release layout: core/assets/gifts_picture/   Dev layout: assets/gifts_picture/
    gifts_pics = root / "core" / "assets" / "gifts_picture"
    if not gifts_pics.exists():
        gifts_pics = root / "assets" / "gifts_picture"
    if gifts_pics.exists():
        app.mount(
            "/gifts-pictures",
            StaticFiles(directory=str(gifts_pics)),
            name="gifts_pictures",
        )

    return app
