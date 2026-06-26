import logging
import time

from fastapi import APIRouter, HTTPException

from core.lifecycle import get_supervisor, ProcessState

log = logging.getLogger(__name__)

router = APIRouter(tags=["Server Lifecycle"])

SERVER_PROCESS_NAME = "Minecraft Server"


def _proc_name(instance_id: str) -> str:
    if instance_id == "default":
        return SERVER_PROCESS_NAME
    return f"{SERVER_PROCESS_NAME}:{instance_id}"


def _build_status(proc) -> dict:
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


# ── Per-instance endpoints ─────────────────────────────────────────


@router.get("/server/{instance_id}/status")
async def server_instance_status(instance_id: str):
    supervisor = get_supervisor()
    proc = supervisor.get(_proc_name(instance_id))
    return _build_status(proc)


@router.post("/server/{instance_id}/start")
async def server_instance_start(instance_id: str):
    supervisor = get_supervisor()
    pname = _proc_name(instance_id)
    proc = supervisor.get(pname)
    if proc is None:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' is not registered")

    if proc.state == ProcessState.RUNNING:
        return {"status": "already_running", "message": f"Server '{instance_id}' is already running"}

    try:
        success = await supervisor.start(pname)
        if success:
            return {"status": "started", "message": f"Server '{instance_id}' started"}
        raise HTTPException(status_code=500, detail=f"Server '{instance_id}' failed to start")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to start server '%s'", instance_id)
        raise HTTPException(status_code=500, detail=f"Failed to start: {e}")


@router.post("/server/{instance_id}/stop")
async def server_instance_stop(instance_id: str):
    supervisor = get_supervisor()
    pname = _proc_name(instance_id)
    proc = supervisor.get(pname)
    if proc is None:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' is not registered")

    if proc.state == ProcessState.STOPPED:
        return {"status": "already_stopped", "message": f"Server '{instance_id}' is already stopped"}

    try:
        success = await supervisor.stop(pname)
        if success:
            return {"status": "stopped", "message": f"Server '{instance_id}' stopped"}
        raise HTTPException(status_code=500, detail=f"Server '{instance_id}' failed to stop")
    except HTTPException:
        raise
    except Exception as e:
        log.exception("Failed to stop server '%s'", instance_id)
        raise HTTPException(status_code=500, detail=f"Failed to stop: {e}")


@router.post("/server/{instance_id}/restart")
async def server_instance_restart(instance_id: str):
    supervisor = get_supervisor()
    pname = _proc_name(instance_id)
    proc = supervisor.get(pname)
    if proc is None:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' is not registered")

    try:
        await supervisor.stop(pname)
        await supervisor.start(pname)
        return {"status": "restarted", "message": f"Server '{instance_id}' restarted"}
    except Exception as e:
        log.exception("Failed to restart server '%s'", instance_id)
        raise HTTPException(status_code=500, detail=f"Failed to restart: {e}")


# ── Legacy default-server endpoints (backward compat) ──────────────


@router.get("/server/status")
async def server_status():
    supervisor = get_supervisor()
    proc = supervisor.get(SERVER_PROCESS_NAME)
    return _build_status(proc)


@router.post("/server/start")
async def server_start():
    return await server_instance_start("default")


@router.post("/server/stop")
async def server_stop():
    return await server_instance_stop("default")


@router.post("/server/restart")
async def server_restart():
    return await server_instance_restart("default")
