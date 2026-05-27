import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import api_router
from .eventbus import event_bus

log = logging.getLogger(__name__)

API_VERSION = "1.0.0"
DEFAULT_PORT = 29185


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("API server v%s starting up ...", API_VERSION)
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
        allow_origins=cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app
