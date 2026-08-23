"""Notification endpoints (J.3 Nr. 13).

Plugins, hooks and the GUI fan out user-facing notifications through
``POST /notifications``; the dispatcher delivers them to the channels
configured in ``config.yaml`` (``notifications.channels``) or to an
explicit per-request channel list.
"""

import logging

from fastapi import APIRouter

from core.api.models import NotificationRequest, NotificationResponse
from core.api.notification_dispatcher import get_notification_dispatcher

log = logging.getLogger(__name__)

router = APIRouter(tags=["Notifications"])


@router.post("/notifications", response_model=NotificationResponse)
async def send_notification(body: NotificationRequest):
    """Fan out one notification to the configured/requested channels."""
    dispatcher = get_notification_dispatcher()
    result = await dispatcher.notify(
        title=body.title,
        body=body.body,
        level=body.level,
        channels=body.channels,
    )
    return NotificationResponse(**result)


@router.get("/notifications/channels")
async def notification_channels():
    """Return the dispatcher status: enabled state and configured channels."""
    return get_notification_dispatcher().status()


@router.post("/notifications/reload")
async def reload_notifications():
    """Re-read the ``notifications`` config section."""
    get_notification_dispatcher().reload()
    return {"status": "ok"}
