import logging
import time

from fastapi import APIRouter, HTTPException

from core.lifecycle import get_supervisor, ProcessState

log = logging.getLogger(__name__)

router = APIRouter(tags=["Server Lifecycle"])

SERVER_PROCESS_NAME = "Minecraft Server"


@router.get("/server/status")
async def server_status():
    supervisor = get_supervisor()
    proc = supervisor.get(SERVER_PROCESS_NAME)
    if proc is None:
        return {
            "status": "unknown",
            "state": "unknown",
            "alive": False,
            "pid": None,
            "uptime": None,
            "restartCount": 0,
        }

    alive = proc.proc is not None and proc.proc.poll() is None
    uptime_seconds = None
    if alive and proc.start_time > 0:
        uptime_seconds = int(time.time() - proc.start_time)

    return {
        "status": proc.state.value,
        "state": proc.state.value,
        "alive": alive,
        "pid": proc.proc.pid if proc.proc and alive else None,
        "uptime": uptime_seconds,
        "restartCount": proc.restart_count,
    }


@router.post("/server/start")
async def server_start():
    supervisor = get_supervisor()
    proc = supervisor.get(SERVER_PROCESS_NAME)
    if proc is None:
        raise HTTPException(status_code=404, detail="Minecraft Server process is not registered")

    if proc.state == ProcessState.RUNNING:
        return {"status": "already_running", "message": "Minecraft Server is already running"}

    try:
        success = await supervisor.start(SERVER_PROCESS_NAME)
        if success:
            return {"status": "started", "message": "Minecraft Server started"}
        raise HTTPException(status_code=500, detail="Minecraft Server failed to start")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to start Minecraft Server")
        raise HTTPException(status_code=500, detail=f"Failed to start: {e}")


@router.post("/server/stop")
async def server_stop():
    supervisor = get_supervisor()
    proc = supervisor.get(SERVER_PROCESS_NAME)
    if proc is None:
        raise HTTPException(status_code=404, detail="Minecraft Server process is not registered")

    if proc.state == ProcessState.STOPPED:
        return {"status": "already_stopped", "message": "Minecraft Server is already stopped"}

    try:
        success = await supervisor.stop(SERVER_PROCESS_NAME)
        if success:
            return {"status": "stopped", "message": "Minecraft Server stopped"}
        raise HTTPException(status_code=500, detail="Minecraft Server failed to stop")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to stop Minecraft Server")
        raise HTTPException(status_code=500, detail=f"Failed to stop: {e}")


@router.post("/server/restart")
async def server_restart():
    supervisor = get_supervisor()
    proc = supervisor.get(SERVER_PROCESS_NAME)
    if proc is None:
        raise HTTPException(status_code=404, detail="Minecraft Server process is not registered")

    try:
        await supervisor.stop(SERVER_PROCESS_NAME)
        await supervisor.start(SERVER_PROCESS_NAME)
        return {"status": "restarted", "message": "Minecraft Server restarted"}
    except Exception as e:
        log.exception("Failed to restart Minecraft Server")
        raise HTTPException(status_code=500, detail=f"Failed to restart: {e}")
