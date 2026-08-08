import asyncio
import logging
import sys
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.java_utils import (
    MIN_JAVA_VERSION,
    detect_java,
    install_java_linux,
    install_java_windows,
)
from core.lifecycle import ProcessState, get_supervisor
from core.minecraft_readiness import make_minecraft_readiness_check
from core.paths import get_base_dir, get_config_file, get_root_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Server Lifecycle"])

SERVER_PROCESS_NAME = "Minecraft Server"
IS_WINDOWS = sys.platform == "win32"
SUFFIX = ".exe" if IS_WINDOWS else ".bin"

# Background Java installation state, polled by the GUI.
_JAVA_INSTALL = {"installing": False, "message": "", "done": False, "ok": False}


def _proc_name(instance_id: str) -> str:
    if instance_id == "default":
        return SERVER_PROCESS_NAME
    return f"{SERVER_PROCESS_NAME}:{instance_id}"


def _java_status_payload() -> dict:
    """Structured Java status for the GUI (detection + install progress)."""
    status = detect_java(get_root_dir(), get_config_file())
    return {
        "ok": status.ok,
        "path": status.path or None,
        "version": status.version or None,
        "source": status.source,
        "reason": status.reason,
        "hints": status.hints,
        "autoInstallable": status.auto_installable,
        "minJavaVersion": MIN_JAVA_VERSION,
        "install": dict(_JAVA_INSTALL),
    }


async def _run_java_install() -> None:
    """Run the platform-appropriate Java installer in the background."""
    _JAVA_INSTALL.update(installing=True, message="Starting Java installation...", done=False, ok=False)
    try:
        if IS_WINDOWS:
            ok, message = await asyncio.to_thread(install_java_windows, get_root_dir())
        else:
            ok, message = await asyncio.to_thread(install_java_linux)
        _JAVA_INSTALL.update(message=message, done=True, ok=ok)
        log.info("Java install finished ok=%s: %s", ok, message)
    except Exception as exc:  # background install: any crash is surfaced via install state
        log.exception("Java installation crashed")
        _JAVA_INSTALL.update(message=f"Java installation crashed: {exc}", done=True, ok=False)
    finally:
        _JAVA_INSTALL["installing"] = False


def _require_java() -> None:
    """Raise a clear HTTP 400 when no usable Java runtime is present.

    This is the pre-flight check: it runs in the API process before any
    Minecraft server subprocess is spawned, so the GUI receives a precise,
    actionable error instead of a generic "failed to start".
    """
    status = detect_java(get_root_dir(), get_config_file())
    if status.ok:
        return
    reason = status.reason or "No suitable Java runtime was found."
    raise HTTPException(
        status_code=400,
        detail=(
            f"Minecraft needs Java {MIN_JAVA_VERSION}+ to start. {reason} "
            f"Use the 'Install Java' button in the Server Manager, or run one of:\n"
            + "\n".join(status.hints)
        ),
    )


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


# ── Java status / install (registered before per-instance routes so that
# the literal path "/server/java/status" wins over "/server/{id}/status") ──


@router.get("/server/java/status")
async def java_status():
    return _java_status_payload()


@router.post("/server/java/install")
async def java_install():
    if _JAVA_INSTALL["installing"]:
        return {
            "status": "in_progress",
            "message": _JAVA_INSTALL["message"] or "Java installation is already in progress...",
        }

    status = detect_java(get_root_dir(), get_config_file())
    if status.ok:
        return {
            "status": "already_installed",
            "message": f"Java {status.version} is already available at {status.path}",
        }
    if not status.auto_installable:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Automatic installation is not supported on this system. "
                f"Install Java {MIN_JAVA_VERSION}+ manually:\n" + "\n".join(status.hints)
            ),
        )

    asyncio.create_task(_run_java_install())
    return {"status": "started", "message": "Java installation started..."}


# ── Per-instance endpoints ─────────────────────────────────────────


@router.get("/server/{instance_id}/status")
async def server_instance_status(instance_id: str):
    supervisor = get_supervisor()
    proc = supervisor.get(_proc_name(instance_id))
    return _build_status(proc)


@router.post("/server/{instance_id}/start")
async def server_instance_start(instance_id: str):
    # Pre-flight: fail fast with a clear message when Java is missing/too old,
    # instead of spawning a subprocess that dies with a cryptic error.
    _require_java()

    supervisor = get_supervisor()
    pname = _proc_name(instance_id)
    proc = supervisor.get(pname)

    # If not registered, dynamically register the instance process
    if proc is None:
        if instance_id == "default":
            raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' is not registered")

        from core.api.routes.servers import _get_instance_dir, _load_instances
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

    # Sync datapack from default server before starting
    try:
        from core.api.routes.servers import _sync_datapack_to_instance
        _sync_datapack_to_instance(instance_id)
    except Exception:  # best-effort sync; server starts with whatever is on disk
        log.warning("[DATAPACK] Failed to sync datapack for '%s' — server will use whatever is on disk", instance_id)

    try:
        success = await supervisor.start(pname)
        if success:
            # Start console capture for this instance
            from core.api.routes.servers import _get_instance_dir
            from core.api.services.console_capture import start_instance_capture
            start_instance_capture(instance_id, _get_instance_dir(instance_id))
            return {"status": "started", "message": f"Server '{instance_id}' started"}
        raise HTTPException(status_code=500, detail=f"Server '{instance_id}' failed to start")
    except HTTPException:
        raise
    except Exception as e:  # any unexpected error becomes an HTTP 500
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
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to stop server '%s'", instance_id)
        raise HTTPException(status_code=500, detail=f"Failed to stop: {e}")


@router.post("/server/{instance_id}/restart")
async def server_instance_restart(instance_id: str):
    supervisor = get_supervisor()
    pname = _proc_name(instance_id)
    proc = supervisor.get(pname)
    if proc is None:
        raise HTTPException(status_code=404, detail=f"Server instance '{instance_id}' is not registered")

    async def _bg_restart():
        try:
            await supervisor.stop(pname)
            await supervisor.start(pname)
        except Exception:  # background restart failures are only logged
            log.exception("Background restart failed for '%s'", instance_id)

    asyncio.create_task(_bg_restart())
    return {"status": "restart_requested", "message": f"Server '{instance_id}' restart initiated"}


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
