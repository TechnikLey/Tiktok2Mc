"""API routes for the Event Tester (trigger simulator).

All endpoints are prefixed with ``/api/v1`` by the central router.

These routes are thin: they collect input from the request, delegate
to ``TriggerService`` (which wraps the shared ``TriggerEngine``), and
return structured responses.  No trigger execution logic lives here.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from core.api.eventbus import event_bus
from core.api.models import (
    TiktokToggleResponse,
    TriggerCommentRequest,
    TriggerExecuteRequest,
    TriggerHistoryEntry,
    TriggerHistoryResponse,
    TriggerResponse,
    TriggerTypesResponse,
)
from core.api.services.trigger_service import get_trigger_service

log = logging.getLogger(__name__)

router = APIRouter(tags=["Triggers"])


@router.get("/triggers/types", response_model=TriggerTypesResponse)
async def list_trigger_types():
    try:
        types = get_trigger_service().get_event_types()
        return TriggerTypesResponse(types=types)
    except Exception as exc:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to list trigger types")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/triggers/execute", response_model=TriggerResponse)
async def execute_trigger(body: TriggerExecuteRequest):
    try:
        # The engine POSTs to the bridge synchronously (up to bridge_timeout).
        # Run it in a thread so a slow/dead bridge cannot stall the event loop.
        result = await asyncio.to_thread(
            get_trigger_service().execute_trigger,
            trigger=body.trigger,
            user=body.user,
            gift_id=body.gift_id,
        )

        event_type = body.trigger
        if body.gift_id:
            event_type = "gift"
        asyncio.ensure_future(
            event_bus.publish(
                f"tiktok.{event_type}",
                {
                    "user": body.user,
                    "gift_id": body.gift_id,
                    "test": True,
                    "source": "trigger_tester",
                },
            )
        )

        return TriggerResponse(
            status=result.get("status", "error"),
            message=result.get("message", ""),
            trigger=body.trigger,
            user=body.user,
        )
    except HTTPException:
        raise
    except Exception as exc:  # any unexpected error becomes an HTTP 500
        log.exception("Trigger execution failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/triggers/dispatch", response_model=TriggerResponse)
async def dispatch_trigger(body: TriggerExecuteRequest):
    """Programmatic trigger execution for extensions (no GUI debounce).

    Unlike ``/triggers/execute`` (Event Tester), this endpoint is never
    rate-limited by the shared tester cooldown and does not mark the
    resulting event as a test event.  Intended for plugins/schedulers that
    fire actions.mca triggers on their own schedule.
    """
    try:
        result = await asyncio.to_thread(
            get_trigger_service().dispatch,
            trigger=body.trigger,
            user=body.user,
            gift_id=body.gift_id,
            gift_name=body.gift_name,
        )

        if result["status"] != "error":
            event_type = body.trigger
            if body.gift_id:
                event_type = "gift"
            asyncio.ensure_future(
                event_bus.publish(
                    f"tiktok.{event_type}",
                    {
                        "user": body.user,
                        "gift_id": body.gift_id,
                        "source": "api",
                    },
                )
            )

        return TriggerResponse(
            status=result.get("status", "error"),
            message=result.get("message", ""),
            trigger=body.trigger,
            user=body.user,
        )
    except HTTPException:
        raise
    except Exception as exc:  # any unexpected error becomes an HTTP 500
        log.exception("Trigger dispatch failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/triggers/tiktok-connection", response_model=TiktokToggleResponse)
async def toggle_tiktok_connection():
    try:
        result = await asyncio.to_thread(get_trigger_service().toggle_tiktok_connection)
        asyncio.ensure_future(
            event_bus.publish(
                "system.tiktok_toggle",
                {
                    "connected": result.get("connected", False),
                    "source": "trigger_tester",
                },
            )
        )
        return TiktokToggleResponse(
            status=result.get("status", "error"),
            message=result.get("message", ""),
            connected=result.get("connected", False),
        )
    except HTTPException:
        raise
    except Exception as exc:  # any unexpected error becomes an HTTP 500
        log.exception("TikTok toggle failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/triggers/comment", response_model=TriggerResponse)
async def send_test_comment(body: TriggerCommentRequest):
    try:
        result = await asyncio.to_thread(
            get_trigger_service().send_comment,
            user=body.user,
            text=body.text,
            moderator=body.moderator,
            superfan=body.superfan,
            fanclub=body.fanclub,
        )
        asyncio.ensure_future(
            event_bus.publish(
                "tiktok.comment",
                {
                    "user": body.user,
                    "text": body.text,
                    "moderator": body.moderator,
                    "superfan": body.superfan,
                    "fanclub": body.fanclub,
                    "test": True,
                    "source": "trigger_tester",
                },
            )
        )
        return TriggerResponse(
            status=result.get("status", "error"),
            message=result.get("message", ""),
            trigger="comment",
            user=body.user,
        )
    except HTTPException:
        raise
    except Exception as exc:  # any unexpected error becomes an HTTP 500
        log.exception("Comment trigger failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/triggers/history", response_model=TriggerHistoryResponse)
async def get_trigger_history():
    try:
        entries = [
            TriggerHistoryEntry(**entry)
            for entry in get_trigger_service().get_history()
        ]
        return TriggerHistoryResponse(history=entries)
    except Exception as exc:  # any unexpected error becomes an HTTP 500
        log.exception("Failed to get trigger history")
        raise HTTPException(status_code=500, detail=str(exc))
