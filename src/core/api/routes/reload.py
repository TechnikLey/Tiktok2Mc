"""Runtime reload endpoint.

Provides a single API call that tells the running system to reload
configuration and/or action definitions without restarting child
processes.  The API server applies the parts it owns immediately; it
also writes signal files that the App bridge process polls.
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.api.eventbus import event_bus
from core.api.services import ApiService
from core.api.services.rcon import get_rcon_service
from core.overlay import get_overlay_manager
from core.paths import get_runtime_dir

log = logging.getLogger(__name__)

router = APIRouter(tags=["Reload"])


class ReloadRequest(BaseModel):
    config: bool = Field(True, description="Reload global config.yaml")
    actions: bool = Field(True, description="Reload data/actions.mca")
    overlay: bool = Field(True, description="Reload overlay settings in the API")
    rcon: bool = Field(True, description="Update API RCON service configuration")
    send_minecraft_reload: bool = Field(
        False,
        description="Ask the App bridge to send /reload to the Minecraft server after reloading actions",
    )


class ReloadResponse(BaseModel):
    status: str
    signals: list[str]


_RUNTIME_DIR: Path = get_runtime_dir()


def _write_signal(name: str, payload: dict | None = None) -> bool:
    """Write a runtime signal file for the App bridge process.

    ``payload`` is serialised as JSON; when omitted the file simply
    contains the string ``"reload"`` for backwards compatibility.
    """
    try:
        _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        signal_file = _RUNTIME_DIR / name
        if payload is not None:
            signal_file.write_text(json.dumps(payload), encoding="utf-8")
        else:
            signal_file.write_text("reload", encoding="utf-8")
        return True
    except Exception as exc:
        log.warning("Failed to write reload signal %s: %s", name, exc)
        return False


@router.post("/reload", response_model=ReloadResponse)
async def reload_runtime(body: ReloadRequest):
    """Request a runtime reload of config and/or actions.

    Safe to call repeatedly.  Invalid configuration is rejected by the
    Config/Actions endpoints before this is reached; this endpoint just
    tells running processes to re-read already-validated files.
    """
    signals: list[str] = []

    if body.config:
        if _write_signal("reload_config"):
            signals.append("reload_config")
        # Update API-owned runtime state that depends on config.
        if body.rcon:
            try:
                cfg = ApiService().read_config()
                rcon_cfg = cfg.get("rcon", {})
                get_rcon_service().configure(
                    host=rcon_cfg.get("host", "localhost"),
                    port=rcon_cfg.get("port", 25575),
                    password=rcon_cfg.get("password", ""),
                )
                log.info("[RELOAD] RCON service configuration updated")
            except Exception as exc:
                log.warning("[RELOAD] Failed to update RCON config: %s", exc)
        if body.overlay:
            try:
                get_overlay_manager().reload()
                log.info("[RELOAD] Overlay settings reloaded")
            except Exception as exc:
                log.warning("[RELOAD] Failed to reload overlay settings: %s", exc)

    if body.actions:
        payload = {"send_minecraft_reload": body.send_minecraft_reload}
        if _write_signal("reload_actions", payload):
            signals.append("reload_actions")

    if not signals:
        raise HTTPException(status_code=400, detail="No reload targets selected")

    await event_bus.publish("system.reload_requested", {
        "config": body.config,
        "actions": body.actions,
    })

    log.info("[RELOAD] Requested signals: %s", signals)
    return ReloadResponse(status="reload_requested", signals=signals)
