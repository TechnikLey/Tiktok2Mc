"""Diagnostics API endpoints — expose runtime health and diagnostics."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.diagnostics import generate_diagnostics_report, generate_diagnostics_markdown
from core.health_monitor import get_health_monitor
from core.error_codes import list_all_codes

log = logging.getLogger(__name__)

router = APIRouter(tags=["Diagnostics"])

_crash_manager = None


def set_crash_manager(cm: Any) -> None:
    global _crash_manager
    _crash_manager = cm


@router.get("/diagnostics")
async def get_diagnostics():
    """Return a full JSON diagnostics report of the application health."""
    try:
        report = generate_diagnostics_report(_crash_manager)
        return report
    except Exception as e:  # noqa: BLE001  # any unexpected error becomes an HTTP 500
        log.exception("Failed to generate diagnostics report")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/markdown")
async def get_diagnostics_markdown():
    """Return a human-readable Markdown diagnostics report."""
    try:
        md = generate_diagnostics_markdown(_crash_manager)
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(md, media_type="text/markdown")
    except Exception as e:  # noqa: BLE001  # any unexpected error becomes an HTTP 500
        log.exception("Failed to generate diagnostics markdown")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/health")
async def get_health_summary():
    """Return a concise health summary."""
    try:
        health = get_health_monitor()
        return health.summary()
    except Exception as e:  # noqa: BLE001  # any unexpected error becomes an HTTP 500
        log.exception("Failed to get health summary")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics/error-codes")
async def get_error_codes(
    subsystem: str | None = Query(None, description="Filter by subsystem prefix"),
):
    """Return all registered error codes, optionally filtered by subsystem."""
    codes = list_all_codes()
    if subsystem:
        codes = [c for c in codes if c.subsystem.value == subsystem.upper()]
    return {
        "total": len(codes),
        "codes": [c.to_dict() for c in codes],
    }


@router.get("/diagnostics/crash-history")
async def get_crash_history():
    """Return the crash history from the crash manager."""
    if _crash_manager is not None:
        return {
            "crash_count": _crash_manager.get_crash_count(),
            "history": _crash_manager.get_crash_history(),
        }
    return {"crash_count": 0, "history": []}
