"""System control endpoints (restart, shutdown signals)."""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

import core.paths
from core.lifecycle import get_supervisor, SupervisorState, shutdown_cancel_event

log = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


def _runtime_dir() -> Path:
    d = core.paths.get_root_dir() / "core" / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/restart")
async def restart_system():
    """Request a clean restart of the backend services.

    The GUI shell survives the restart and reloads when the API comes back.
    """
    supervisor = get_supervisor()
    if supervisor.state not in {
        SupervisorState.IDLE,
        SupervisorState.STARTING,
        SupervisorState.RUNNING,
    }:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot restart while supervisor is in state {supervisor.state.value}",
        )
    try:
        asyncio.create_task(supervisor.restart())
        log.info("Restart requested via API")
        return {"status": "restart_requested"}
    except Exception as e:
        log.exception("Failed to request restart")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
async def shutdown_system():
    """Request a graceful shutdown with countdown."""
    supervisor = get_supervisor()
    if supervisor.state == SupervisorState.SHUTTING_DOWN:
        return {"status": "shutdown_already_requested"}
    if supervisor.state == SupervisorState.COMPLETE:
        raise HTTPException(status_code=409, detail="Already shut down")
    try:
        asyncio.create_task(supervisor.shutdown_countdown())
        log.info("Shutdown requested via API (delay %ss)", supervisor.shutdown_delay)
        return {"status": "shutdown_requested"}
    except Exception as e:
        log.exception("Failed to request shutdown")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown/now")
async def shutdown_now():
    """Request an immediate shutdown — skips countdown entirely."""
    supervisor = get_supervisor()
    if supervisor.state == SupervisorState.COMPLETE:
        raise HTTPException(status_code=409, detail="Already shut down")
    try:
        shutdown_cancel_event.set()
        asyncio.create_task(supervisor.shutdown())
        log.info("Immediate shutdown requested via API")
        return {"status": "shutdown_now"}
    except Exception as e:
        log.exception("Failed to request immediate shutdown")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shutdown/status")
async def shutdown_status():
    """Return the current shutdown state (countdown, shutting_down, etc.)."""
    try:
        status_file = _runtime_dir() / "shutdown_status"
        if status_file.exists():
            raw = status_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            remaining = data.get("remaining")
            state = data.get("state", "idle")
            return {
                "shutdown_pending": remaining is not None,
                "remaining_seconds": remaining,
                "state": state,
            }
        return {"shutdown_pending": False, "remaining_seconds": None, "state": "idle"}
    except Exception as e:
        log.exception("Failed to read shutdown status")
        return {"shutdown_pending": False, "remaining_seconds": None, "state": "idle"}


@router.post("/shutdown/cancel")
async def shutdown_cancel():
    """Cancel an active shutdown countdown."""
    try:
        shutdown_cancel_event.set()
        log.info("Shutdown cancel requested via API")
        return {"status": "cancel_requested"}
    except Exception as e:
        log.exception("Failed to cancel shutdown")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/server/restart")
async def restart_server():
    """Request a restart of the Minecraft Server process.

    The supervisor (start.py) watches for the ``restart_server`` runtime
    signal and restarts only the ``Minecraft Server`` child process.
    """
    try:
        signal_file = _runtime_dir() / "restart_server"
        signal_file.write_text("restart", encoding="utf-8")
        log.info("Minecraft Server restart requested via API")
        return {"status": "server_restart_requested"}
    except Exception as e:
        log.exception("Failed to request Minecraft Server restart")
        raise HTTPException(status_code=500, detail=str(e))
