"""Updater signal endpoints + tool update check.

Provides a simple in-memory kill signal mechanism so the updater
process can request that ``start.py`` shut down (for file replacement
during updates) without relying solely on a temp file.
Also provides ``GET /updates/check`` for tool version checking
and ``POST /updates/apply`` to trigger a manual update.
"""

import asyncio
import logging
import subprocess
import sys

from fastapi import APIRouter, HTTPException

from core.api.models import (
    ToolUpdateApplyResponse,
    ToolUpdateCheckResponse,
    UpdateResultResponse,
)
from core.api.updater import check_tool_update, get_last_update_result
from core.paths import get_base_dir
from core.version import TOOL_VERSION

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
    and compares the latest tag with the current ``TOOL_VERSION``
    (the tag and the tool version are the same release number).
    """
    try:
        result = check_tool_update(TOOL_VERSION)
        return ToolUpdateCheckResponse(**result)
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to check tool updates")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/updates/result", response_model=UpdateResultResponse)
async def tool_update_result():
    """Return the last tool-update result recorded by ``start.py``."""
    result = get_last_update_result()
    if result is None:
        return UpdateResultResponse()
    return UpdateResultResponse(**result)


# ── Manual update apply ──────────────────────────────────────────────


@router.get("/updates/auto_install")
async def get_auto_install():
    """Return whether auto-install is enabled in the config."""
    from core.api.services import ApiService

    try:
        svc = ApiService()
        cfg = svc.read_config()
    except (FileNotFoundError, Exception):
        cfg = {}
    return {"auto_install": cfg.get("update", {}).get("auto_install", True)}


@router.post("/updates/apply", response_model=ToolUpdateApplyResponse)
async def apply_update():
    """Trigger the updater binary to install the latest version.

    Spawns the updater process with ``--auto`` in the background.
    The updater will signal ``start.py`` to shut down, replace files,
    and restart the application.
    """
    base_dir = get_base_dir()
    suffix = ".exe" if sys.platform == "win32" else ".bin"
    update_path = base_dir / f"update{suffix}"

    if not update_path.exists():
        log.warning("Updater binary not found at %s", update_path)
        raise HTTPException(
            status_code=404,
            detail="Updater binary not found",
        )

    try:
        cmd = [str(update_path), "--auto"]
        if sys.platform == "win32":
            await asyncio.to_thread(
                subprocess.Popen,
                cmd,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            await asyncio.to_thread(
                subprocess.Popen,
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        log.info("Updater triggered manually via GUI")
        return ToolUpdateApplyResponse(
            status="started",
            message="Updater process started. The application will restart when done.",
        )
    except Exception as e:
        log.exception("Failed to start updater")
        raise HTTPException(status_code=500, detail=str(e))
