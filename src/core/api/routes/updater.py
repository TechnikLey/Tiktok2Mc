"""Updater signal endpoints + tool update check.

Provides a simple in-memory kill signal mechanism so the updater
process can request that ``start.py`` shut down (for file replacement
during updates) without relying solely on a temp file.
Also provides ``GET /updates/check`` for tool version checking.
"""

import logging

from fastapi import APIRouter, HTTPException

from core.api.models import API_VERSION, ToolUpdateCheckResponse
from core.api.updater import check_tool_update

log = logging.getLogger(__name__)

router = APIRouter(tags=["Updater"])

_kill_signal: str | None = None


@router.get("/updater/signal")
async def get_signal():
    """Return the current kill signal, or ``None``."""
    return {"signal": _kill_signal}


@router.put("/updater/signal")
async def set_signal(body: dict):
    """Set a kill signal (e.g. ``{"signal": "kill"}``)."""
    global _kill_signal
    _kill_signal = body.get("signal")
    return {"signal": _kill_signal}


@router.delete("/updater/signal")
async def clear_signal():
    """Clear the kill signal."""
    global _kill_signal
    _kill_signal = None
    return {"signal": None}


# ── Tool update check ────────────────────────────────────────────────


@router.get("/updates/check", response_model=ToolUpdateCheckResponse)
async def tool_update_check():
    """Check the main repo for a newer tool release.

    Queries ``TechnikLey/Tiktok2Mc`` via the GitHub Releases API
    and compares the latest tag with the current ``API_VERSION``.
    """
    try:
        result = check_tool_update(API_VERSION)
        return ToolUpdateCheckResponse(**result)
    except Exception as e:  # noqa: BLE001  # any unexpected error becomes an HTTP 500
        log.exception("Failed to check tool updates")
        raise HTTPException(status_code=500, detail=str(e))
