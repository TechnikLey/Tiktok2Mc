"""System control endpoints (restart signals)."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from core.lifecycle import SupervisorState, get_supervisor
from core.shutdown import ShutdownReason, get_shutdown_controller

log = logging.getLogger(__name__)

router = APIRouter(tags=["System"])


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
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to request restart")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown/now")
async def shutdown_now():
    """Trigger immediate shutdown of the entire application.

    Routes through the ShutdownController for proper diagnostics.
    The caller (GUI) gets an immediate response; the actual shutdown
    runs asynchronously with full logging and forensic state tracking.
    """
    ctrl = get_shutdown_controller()
    request = ctrl.request_shutdown(
        reason=ShutdownReason.USER_REQUEST,
        source="api:/api/v1/shutdown/now",
    )
    if request is None:
        return {
            "status": "shutdown_already_pending",
            "shutdown_id": ctrl.accepted_request.id if ctrl.accepted_request else None,
        }

    log.info("Shutdown requested via API (ID: %s)", request.id)
    return {"status": "shutdown_requested", "shutdown_id": request.id}
