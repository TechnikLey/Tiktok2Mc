import asyncio
import logging
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.lifecycle import get_supervisor, ProcessState
from core.minecraft_readiness import make_minecraft_readiness_check
from core.paths import get_base_dir, get_servers_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Server Lifecycle"])

SERVER_PROCESS_NAME = "Minecraft Server"
IS_WINDOWS = sys.platform == "win32"
SUFFIX = ".exe" if IS_WINDOWS else ".bin"


def _proc_name(instance_id: str) -> str:
    if instance_id == "default":
        return SERVER_PROCESS_NAME
    return f"{SERVER_PROCESS_NAME}:{instance_id}"


def _find_server_exe() -> Path | None:
    """Locate the Minecraft server executable/binary or source script."""
    base = get_base_dir()
    candidates = [
        base / "core" / f"server{SUFFIX}",
        base / f"server{SUFFIX}",
        base.parent / "core" / f"server{SUFFIX}",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    # Development fallback: server.py
    dev_server = Path(__file__).resolve().parent.parent.parent.parent / "python" / "server.py"
    if dev_server.exists():
        return dev_server
    return None


def _build_server_cmd(instance_dir: Path, port: int) -> list[str]:
    """Build the command list to start a Minecraft server instance."""
    server_exe = _find_server_exe()
    if server_exe is None:
        raise HTTPException(status_code=500, detail="Minecraft server executable not found")

    cmd: list[str] = []
    if server_exe.suffix == ".py":
        cmd.append(sys.executable)
    cmd.append(str(server_exe))
    cmd.extend(["--instance-dir", str(instance_dir), "--port", str(port)])
    return cmd


# ---------------------------------------------------------------------------
# Status builder
# ---------------------------------------------------------------------------

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
    if alive and proc.start_time > 0 and proc.state == ProcessState.RUNNING:
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

    # If not registered, dynamically register the instance process
    if proc is None:
        if instance_id == "default":
            raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' is not registered")

        from core.api.routes.servers import _load_instances, _get_instance_dir
        instances = _load_instances()
        if instance_id not in instances:
            raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' not found in configuration")

        inst_data = instances[instance_id]
        instance_dir = _get_instance_dir(instance_id)
        jar_path = instance_dir / "server.jar"
        if not jar_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Instance '{instance_id}' does not have a server.jar. Create the instance first.",
            )

        port = inst_data.get("port", 25565)
        try:
            cmd = _build_server_cmd(instance_dir, port)
        except HTTPException:
            raise

        try:
            proc = supervisor.register(
                pname,
                cmd,
                cwd=instance_dir,
                hidden=True,
                readiness_check=make_minecraft_readiness_check(instance_dir),
                readiness_timeout=120.0,
            )
            log.info("Dynamically registered server process '%s' with cmd: %s", pname, cmd)
        except ValueError:
            # Race: already registered between our get() and register()
            proc = supervisor.get(pname)
            if proc is None:
                raise HTTPException(status_code=500, detail="Failed to register process")

    if proc.state == ProcessState.RUNNING:
        return {"status": "already_running", "message": f"Server '{instance_id}' is already running"}

    try:
        success = await supervisor.start(pname)
        if success:
            # Start console capture for this instance
            from core.api.services.console_capture import start_instance_capture
            from core.api.routes.servers import _get_instance_dir
            start_instance_capture(instance_id, _get_instance_dir(instance_id))
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
            # Stop console capture for this instance
            from core.api.services.console_capture import stop_instance_capture
            stop_instance_capture(instance_id)
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
