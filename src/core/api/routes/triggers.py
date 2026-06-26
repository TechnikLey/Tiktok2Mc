"""API routes for the Event Tester (trigger simulator).

All endpoints are prefixed with ``/api/v1`` by the central router.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from core.api.models import (
    TriggerCommentRequest,
    TriggerExecuteRequest,
    TriggerHistoryResponse,
    TriggerResponse,
    TriggerTypesResponse,
    TiktokToggleResponse,
)
from core.api.services.trigger_service import get_trigger_service

log = logging.getLogger(__name__)

router = APIRouter(tags=["Triggers"])


@router.get("/triggers/types", response_model=TriggerTypesResponse)
async def list_trigger_types():
    """Return the predefined trigger/event types available for testing."""
    try:
        types = get_trigger_service().get_event_types()
        return TriggerTypesResponse(types=types)
    except Exception as exc:
        log.exception("Failed to list trigger types")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/triggers/execute", response_model=TriggerResponse)
async def execute_trigger(body: TriggerExecuteRequest):
    """Execute a simulated trigger event.

    The trigger flows through the same pipeline as a real TikTok event so
    that test behaviour is indistinguishable from production behaviour.
    """
    try:
        result = get_trigger_service().execute_trigger(
            trigger=body.trigger,
            user=body.user,
            gift_id=body.gift_id,
        )
        return TriggerResponse(
            status=result.get("status", "error"),
            message=result.get("message", ""),
            trigger=body.trigger,
            user=body.user,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Trigger execution failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/triggers/tiktok-connection", response_model=TiktokToggleResponse)
async def toggle_tiktok_connection():
    """Toggle the TikTok live-stream connection on/off.

    This is a system control operation, not an event simulation.
    It directly toggles the bridge's ``disable_tiktok_connect`` flag.
    """
    try:
        result = get_trigger_service().toggle_tiktok_connection()
        return TiktokToggleResponse(
            status=result.get("status", "error"),
            message=result.get("message", ""),
            connected=result.get("connected", False),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("TikTok toggle failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/triggers/comment", response_model=TriggerResponse)
async def send_test_comment(body: TriggerCommentRequest):
    """Execute a simulated comment event.

    The comment flows through the same pipeline as a real TikTok comment so
    that test behaviour is indistinguishable from production behaviour.
    """
    try:
        result = get_trigger_service().send_comment(
            user=body.user,
            text=body.text,
            moderator=body.moderator,
            superfan=body.superfan,
            fanclub=body.fanclub,
        )
        return TriggerResponse(
            status=result.get("status", "error"),
            message=result.get("message", ""),
            trigger="comment",
            user=body.user,
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Comment trigger failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/triggers/history", response_model=TriggerHistoryResponse)
async def get_trigger_history():
    """Return the in-memory session history of triggered events."""
    try:
        entries = get_trigger_service().get_history()
        return TriggerHistoryResponse(history=entries)
    except Exception as exc:
        log.exception("Failed to get trigger history")
        raise HTTPException(status_code=500, detail=str(exc))
