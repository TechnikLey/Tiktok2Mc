"""Session summary, detail and report endpoints (per-stream report viewer)."""

import logging

from fastapi import APIRouter, HTTPException, Query

from core.api.models import SessionDetailResponse, SessionsResponse
from core.api.services.analytics import AnalyticsService
from core.api.services.sessions import SessionService

log = logging.getLogger(__name__)

router = APIRouter(tags=["Sessions"])
_service: AnalyticsService | SessionService | None = None


def _get_service() -> AnalyticsService | SessionService:
    """Return the process-wide sessions service.

    Production uses :class:`AnalyticsService` (SQLite with JSONL fallback).
    Tests may monkeypatch this function with a plain :class:`SessionService`.
    """
    global _service
    if _service is None:
        _service = AnalyticsService()
    return _service


@router.get("/sessions", response_model=SessionsResponse)
async def get_sessions(
    limit: int = Query(100, ge=1, le=500, description="Maximum sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
):
    """Return paginated stream sessions plus all-time totals.

    Entries are newest first. When the analytics database is unavailable the
    legacy ``sessions.jsonl`` log is used instead.
    """
    service = _get_service()
    if isinstance(service, AnalyticsService):
        return service.summary_page(limit=limit, offset=offset)
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


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(session_id: str):
    """Return one session with per-viewer, per-gift and top-list detail.

    Legacy sessions imported from ``sessions.jsonl`` only carry totals, so
    their detail lists are empty.
    """
    service = _get_service()
    if not isinstance(service, AnalyticsService):
        raise HTTPException(status_code=404, detail="Session detail unavailable")
    detail = service.get_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return detail
