"""Chatbot configuration and status endpoints.

The chatbot config lives in its own file (``config/chatbot.yaml``) so a
GUI round-trip never touches the global ``config.yaml``.  Saving writes
a ``reload_chatbot`` runtime signal that the bridge picks up within a
second — same mechanism as the other reload signals.
"""

import logging

from fastapi import APIRouter, HTTPException

from core.api.chatbot_status import get_chatbot_status_tracker
from core.api.models import (
    ChatbotConfigResponse,
    ChatbotConfigUpdateRequest,
    ChatbotStatusResponse,
)
from core.paths import get_chatbot_config_file, get_runtime_dir
from core.yaml_utils import load_yaml, save_yaml

log = logging.getLogger(__name__)

router = APIRouter(tags=["Chatbot"])


@router.get("/chatbot/config", response_model=ChatbotConfigResponse)
async def get_chatbot_config():
    """Return the chatbot config; defaults when no file exists yet."""
    path = get_chatbot_config_file()
    try:
        if not path.exists():
            return ChatbotConfigResponse(path=str(path), chatbot={})
        data = load_yaml(path)
        return ChatbotConfigResponse(path=str(path), chatbot=data if data else {})
    except Exception as e:  # any unexpected error becomes an HTTP 500
        log.error("Failed to load chatbot config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/chatbot/config", response_model=ChatbotConfigResponse)
async def update_chatbot_config(body: ChatbotConfigUpdateRequest):
    """Persist the chatbot config and ask the bridge to hot-reload it."""
    path = get_chatbot_config_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(path, body.chatbot, backup=True)
    except Exception as e:
        log.error("Failed to write chatbot config: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    signal = get_runtime_dir() / "reload_chatbot"
    try:
        signal.parent.mkdir(parents=True, exist_ok=True)
        signal.write_text("reload", encoding="utf-8")
    except OSError as exc:
        # Config is saved; only the live reload of the bridge failed.
        log.warning("Failed to write chatbot reload signal: %s", exc)
        return ChatbotConfigResponse(
            path=str(path), chatbot=body.chatbot, reloaded=False
        )

    return ChatbotConfigResponse(path=str(path), chatbot=body.chatbot, reloaded=True)


@router.get("/chatbot/status", response_model=ChatbotStatusResponse)
async def get_chatbot_status():
    """Last known chatbot status reported by the bridge (None if stale)."""
    return ChatbotStatusResponse(status=get_chatbot_status_tracker().snapshot())
