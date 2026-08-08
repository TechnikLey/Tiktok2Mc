import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.status import HTTP_401_UNAUTHORIZED

from core.overlay import set_event_loop
from core.paths import get_root_dir

from .dashboard_publisher import get_dashboard_publisher
from .eventbus import event_bus
from .models import API_VERSION
from .plugin_health import get_health_monitor
from .plugin_overlay import command_queue
from .plugin_watcher import get_plugin_watcher
from .routes import api_router
from .services import ApiService
from .services.rcon import get_rcon_service
from .tiktok_live import get_tiktok_live_tracker

log = logging.getLogger(__name__)

DEFAULT_PORT = 29185

_LOCALHOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _discover_hooks_at_startup() -> None:
    """Auto-discover hooks from filesystem and populate the hook registry.

    Mirrors what PluginWatcher does for plugins — ensures hooks appear
    in the GUI immediately without waiting for the bridge process.
    """
    try:
        from core.hook_loader import _discover_hook_dirs
        from core.hook_registry import get_hook_registry

        discovered = _discover_hook_dirs()
        hook_infos = []
        for info in discovered:
            hook_infos.append({
                "name": info["name"],
                "version": info["version"],
                "display_name": info["display_name"],
                "description": info["description"],
                "author": info["author"],
                "capabilities": info["capabilities"],
                "plugin": info["plugin"],
                "update_url": info["update_url"],
                "source": info["source"],
            })
        registry = get_hook_registry()
        new_count = registry.sync_from_discovery(hook_infos)
        active_names = {info["name"] for info in discovered}
        cleaned = registry.clean_stale(active_names)
        if new_count or cleaned:
            log.info(
                "[HOOK] Auto-discovered: %d new, %d removed at startup",
                new_count, cleaned,
            )
        else:
            log.info("[HOOK] Auto-discovered %d hook(s) at startup", len(discovered))
    except Exception as exc:  # hook discovery must never block API startup
        log.warning("[HOOK] Auto-discovery at startup failed: %s", exc)


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
    _discover_hooks_at_startup()
    await get_health_monitor().start()
    get_event_command_mapper().start()
    get_dashboard_publisher().start()
    get_tiktok_live_tracker().start()
    # Pre-configure RCON from config for the console feature
    try:
        cfg = ApiService().read_config()
        rcon_cfg = cfg.get("rcon", {})
        get_rcon_service().configure(
            host=rcon_cfg.get("host", "localhost"),
            port=rcon_cfg.get("port", 25575),
            password=rcon_cfg.get("password", ""),
        )
    except Exception:  # RCON is optional; console auto-configures on first request
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
        await get_tiktok_live_tracker().stop()
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

    class CancelledErrorMiddleware:
        """Suppress CancelledError spam when clients disconnect or the server shuts down."""
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return
            try:
                await self.app(scope, receive, send)
            except asyncio.CancelledError:
                # Client disconnected or the supervisor is shutting down.
                # Send a 499 (client closed request) if possible, then stop.
                try:
                    await send({"type": "http.response.start", "status": 499, "headers": []})
                    await send({"type": "http.response.body", "body": b""})
                except Exception:  # client already gone; nothing more to do
                    pass

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
