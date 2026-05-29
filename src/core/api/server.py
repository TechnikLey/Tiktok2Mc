import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles

from .routes import api_router
from .eventbus import event_bus
from .models import API_VERSION
from core.paths import get_root_dir

log = logging.getLogger(__name__)

DEFAULT_PORT = 29185


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("API server v%s starting up ...", API_VERSION)
    log.info(
        "CORS origin restricted to localhost — "
        "use create_app(cors_origins=[\"*\"]) to open for development"
    )
    await event_bus.publish("server.started", {"version": API_VERSION})
    yield
    await event_bus.publish("server.stopping", {})
    log.info("API server shutting down ...")


def create_app(
    title: str = "TikTok2MC API",
    version: str = API_VERSION,
    cors_origins: list[str] | None = None,
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

    app.include_router(api_router)

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
