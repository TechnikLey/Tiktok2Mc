"""System control endpoints (restart signals)."""

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException

from core.lifecycle import get_supervisor, SupervisorState

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
    except Exception as e:
        log.exception("Failed to request restart")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown/now")
async def shutdown_now():
    """Trigger immediate shutdown of the entire application."""
    log.info("Shutdown requested via API – shutting down supervisor then exiting")

    async def _delayed_exit():
        await asyncio.sleep(0.3)
        try:
            supervisor = get_supervisor()
            await supervisor.shutdown()
        except Exception:
            log.exception("Supervisor shutdown failed, exiting directly")
        finally:
            os._exit(0)

    asyncio.create_task(_delayed_exit())
    return {"status": "shutdown_requested"}
