"""Chatbot configuration, session and status endpoints.

The chatbot config lives in its own file (``config/chatbot.yaml``) so a
GUI round-trip never touches the global ``config.yaml``.  Saving writes
a ``reload_chatbot`` runtime signal that the bridge picks up within a
second — same mechanism as the other reload signals.

Session credentials (TikTok ``sessionid`` cookie) are stored encrypted
in ``data/chatbot_session.json`` via :mod:`core.chatbot_session` —
never in plaintext config files.  The API only ever returns a masked
preview, the raw value stays local.
"""

import logging

from fastapi import APIRouter, HTTPException

from core.api.chatbot_status import get_chatbot_status_tracker
from core.api.models import (
    ChatbotConfigResponse,
    ChatbotConfigUpdateRequest,
    ChatbotSessionResponse,
    ChatbotSessionUpdateRequest,
    ChatbotStatusResponse,
)
from core.chatbot_session import (
    SessionValidationError,
    clear_chatbot_session,
    get_chatbot_session_info,
    request_bridge_reload,
    save_chatbot_session,
)
from core.paths import get_chatbot_config_file
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

    reloaded = request_bridge_reload()
    return ChatbotConfigResponse(
        path=str(path), chatbot=body.chatbot, reloaded=reloaded
    )


@router.get("/chatbot/session", response_model=ChatbotSessionResponse)
async def get_chatbot_session():
    """Secret-free info about the stored TikTok session credentials."""
    return ChatbotSessionResponse(**get_chatbot_session_info())


@router.put("/chatbot/session", response_model=ChatbotSessionResponse)
async def update_chatbot_session(body: ChatbotSessionUpdateRequest):
    """Encrypt and store new session credentials (manual login, CHATBOT.md §4)."""
    try:
        info = save_chatbot_session(body.session_id, body.tt_target_idc)
    except SessionValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except OSError as e:
        log.error("Failed to store chatbot session: %s", e)
        raise HTTPException(status_code=500, detail="session storage failed")

    # The bridge applies credentials at the next connect; the signal also
    # refreshes its config view so an enabled bot picks everything up.
    reloaded = request_bridge_reload()
    if not reloaded:
        log.info("Session saved but bridge reload signal failed")
    return ChatbotSessionResponse(**info)


@router.delete("/chatbot/session", response_model=ChatbotSessionResponse)
async def delete_chatbot_session():
    """Remove stored session credentials."""
    try:
        clear_chatbot_session()
    except OSError as e:
        log.error("Failed to clear chatbot session: %s", e)
        raise HTTPException(status_code=500, detail="session storage failed")
    return ChatbotSessionResponse(**get_chatbot_session_info())


@router.get("/chatbot/status", response_model=ChatbotStatusResponse)
async def get_chatbot_status():
    """Last known chatbot status reported by the bridge (None if stale)."""
    return ChatbotStatusResponse(status=get_chatbot_status_tracker().snapshot())
