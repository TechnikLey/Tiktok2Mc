"""Session summary endpoints (per-stream report viewer)."""

import logging

from fastapi import APIRouter, HTTPException

from core.api.models import SessionsResponse
from core.api.services.sessions import SessionService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Sessions"])
_service: SessionService | None = None


def _get_service() -> SessionService:
    global _service
    if _service is None:
        _service = SessionService()
    return _service


@router.get("/sessions", response_model=SessionsResponse)
async def get_sessions():
    """Return all recorded stream sessions plus totals."""
    service = _get_service()
    return service.summary()


@router.get("/sessions/report")
async def get_sessions_report():
    """Return a human-readable Markdown report of all stream sessions."""
    from fastapi.responses import PlainTextResponse

    try:
        md = _get_service().generate_markdown()
        return PlainTextResponse(md, media_type="text/markdown")
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to generate sessions report")
        raise HTTPException(status_code=500, detail=str(e))
