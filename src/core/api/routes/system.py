"""System control endpoints (restart, shutdown signals)."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.paths import get_root_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


def _runtime_dir() -> Path:
    d = get_root_dir() / "core" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/restart")
async def restart_system():
    """Write a restart signal that start.py picks up via file watcher."""
    try:
        signal_file = _runtime_dir() / "restart"
        signal_file.write_text("", encoding="utf-8")
        log.info("Restart signal written to %s", signal_file)
        return {"status": "restart_requested"}
    except Exception as e:
        log.exception("Failed to write restart signal")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
async def shutdown_system():
    """Write a shutdown signal that start.py picks up via file watcher."""
    try:
        signal_file = _runtime_dir() / "shutdown"
        signal_file.write_text("", encoding="utf-8")
        log.info("Shutdown signal written to %s", signal_file)
        return {"status": "shutdown_requested"}
    except Exception as e:
        log.exception("Failed to write shutdown signal")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown/now")
async def shutdown_now():
    """Write an immediate shutdown signal — skips countdown entirely."""
    try:
        signal_file = _runtime_dir() / "shutdown_now"
        signal_file.write_text("", encoding="utf-8")
        log.info("Immediate shutdown signal written to %s", signal_file)
        return {"status": "shutdown_now"}
    except Exception as e:
        log.exception("Failed to write immediate shutdown signal")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shutdown/status")
async def shutdown_status():
    """Return the current countdown state (``null`` when no countdown is active)."""
    try:
        status_file = _runtime_dir() / "shutdown_status"
        if status_file.exists():
            raw = status_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            remaining = data.get("remaining")
            return {
                "shutdown_pending": remaining is not None,
                "remaining_seconds": remaining,
            }
        return {"shutdown_pending": False, "remaining_seconds": None}
    except Exception as e:
        log.exception("Failed to read shutdown status")
        return {"shutdown_pending": False, "remaining_seconds": None}


@router.post("/shutdown/cancel")
async def shutdown_cancel():
    """Cancel an active shutdown countdown by writing a cancel signal."""
    try:
        signal_file = _runtime_dir() / "shutdown_cancel"
        signal_file.write_text("", encoding="utf-8")
        log.info("Shutdown cancel signal written to %s", signal_file)
        return {"status": "cancel_requested"}
    except Exception as e:
        log.exception("Failed to write shutdown cancel signal")
        raise HTTPException(status_code=500, detail=str(e))
