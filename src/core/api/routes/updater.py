"""Updater signal endpoints.

Provides a simple in-memory kill signal mechanism so the updater
process can request that ``start.py`` shut down (for file replacement
during updates) without relying solely on a temp file.
"""

import logging

from fastapi import APIRouter

log = logging.getLogger(__name__)

router = APIRouter(tags=["Updater"])

_kill_signal: str | None = None


@router.get("/updater/signal")
async def get_signal():
    """Return the current kill signal, or ``None``."""
    return {"signal": _kill_signal}


@router.put("/updater/signal")
async def set_signal(body: dict):
    """Set a kill signal (e.g. ``{"signal": "kill"}``)."""
    global _kill_signal
    _kill_signal = body.get("signal")
    return {"signal": _kill_signal}


@router.delete("/updater/signal")
async def clear_signal():
    """Clear the kill signal."""
    global _kill_signal
    _kill_signal = None
    return {"signal": None}
