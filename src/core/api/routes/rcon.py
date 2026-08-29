import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.api.services import ApiService
from core.api.services.console_capture import (
    start_instance_capture,
    stop_instance_capture,
)
from core.api.services.rcon import get_rcon_service
from core.error_codes import MC_0012
from core.paths import get_root_dir

log = logging.getLogger(__name__)

router = APIRouter(prefix="/rcon", tags=["RCON"])

_api_service: ApiService | None = None


def _get_api_service() -> ApiService:
    global _api_service
    if _api_service is None:
        _api_service = ApiService()
    return _api_service


def _command_api_enabled() -> bool:
    """Whether the direct RCON HTTP endpoint may execute commands.

    Gated by ``rcon.http_command_api`` (default ``false`` for security and
    stability — the endpoint bypasses the bridge's RCON queue and
    throttling). The dashboard Console needs it enabled; the queue path
    used by actions/hooks keeps working either way.
    """
    config = _get_api_service().read_config()
    return bool(config.get("rcon", {}).get("http_command_api", False))


def _configure_from_config():
    svc = get_rcon_service()
    config = _get_api_service().read_config()
    rcon_cfg = config.get("rcon", {})
    svc.configure(
        host=rcon_cfg.get("host", "localhost"),
        port=rcon_cfg.get("port", 25575),
        password=rcon_cfg.get("password", ""),
    )


class CommandRequest(BaseModel):
    command: str


class CommandResponse(BaseModel):
    response: str


class StatusResponse(BaseModel):
    connected: bool
    host: str
    port: int


@router.get("/status", response_model=StatusResponse)
async def get_status():
    svc = get_rcon_service()
    _configure_from_config()
    return StatusResponse(
        connected=svc.connected,
        host=svc.host,
        port=svc.port,
    )


@router.post("/connect")
async def connect():
    svc = get_rcon_service()
    _configure_from_config()
    ok = await svc.connect()
    if not ok:
        raise HTTPException(status_code=502, detail="RCON connection failed")
    # Start console log capture so server.console events flow to the GUI
    server_dir = get_root_dir() / "server" / "default"
    start_instance_capture("default", server_dir)
    return {"status": "connected"}


@router.post("/disconnect")
async def disconnect():
    svc = get_rcon_service()
    await svc.disconnect()
    stop_instance_capture("default")
    return {"status": "disconnected"}


@router.post("/command", response_model=CommandResponse)
async def send_command(req: CommandRequest):
    if not _command_api_enabled():
        log.warning(
            "%s rejected direct RCON command (rcon.http_command_api=false)",
            MC_0012.code,
        )
        raise HTTPException(
            status_code=403,
            detail=f"{MC_0012.code} {MC_0012.message}",
        )
    svc = get_rcon_service()
    if not svc.connected:
        _configure_from_config()
        ok = await svc.connect()
        if not ok:
            raise HTTPException(status_code=502, detail="RCON not connected")
    try:
        resp = await svc.command(req.command)
        return CommandResponse(response=resp)
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))
